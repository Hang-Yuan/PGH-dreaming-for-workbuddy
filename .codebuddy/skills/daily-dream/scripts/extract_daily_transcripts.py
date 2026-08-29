#!/usr/bin/env python3
"""Extract one logical day of human WorkBuddy project conversations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[4]
DEFAULT_PROJECTS = Path.home() / ".workbuddy" / "projects"
DEFAULT_DATABASE = Path.home() / ".workbuddy" / "workbuddy.db"
USER_QUERY = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)
VISIBLE_TYPES = {"input_text", "output_text", "text"}
SCAFFOLD_PREFIXES = (
    "<recommended_plugins>",
    "# CODEBUDDY.md instructions",
    "<environment_context>",
    "<workbuddy_internal_context",
    "<turn_aborted>",
)


@dataclass(frozen=True)
class SessionMeta:
    session_id: str
    cwd: str
    background_automation: bool


@dataclass(frozen=True)
class Message:
    timestamp: int
    local_time: str
    session_id: str
    role: str
    text: str
    source_file: str
    source_line: int
    source_line_sha256: str


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="logical date in YYYY-MM-DD form")
    parser.add_argument("--timezone")
    parser.add_argument("--boundary-hour", type=int)
    parser.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--scope", choices=("project", "all"), default=None)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def load_authority(
    explicit_timezone: str | None, explicit_boundary: int | None
) -> tuple[str, int, str | None]:
    state_path = ROOT / ".pgh" / "state.json"
    state: dict = {}
    if state_path.exists():
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            state = raw
    timezone_name = explicit_timezone or state.get("timezone")
    boundary = explicit_boundary if explicit_boundary is not None else state.get("boundary_hour")
    l0_scope = state.get("l0_scope")
    if l0_scope not in ("project", "all"):
        l0_scope = None
    if not isinstance(timezone_name, str):
        raise RuntimeError("timezone is missing; finish PGH basic initialization or pass --timezone")
    ZoneInfo(timezone_name)
    if not isinstance(boundary, int) or isinstance(boundary, bool) or not 0 <= boundary <= 23:
        raise RuntimeError("boundary hour is missing or invalid")
    return timezone_name, boundary, l0_scope


def session_index(database: Path) -> dict[str, SessionMeta]:
    if not database.is_file():
        raise RuntimeError("WorkBuddy session index is unavailable; refusing unclassified L0 extraction")
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT id, cwd, COALESCE(is_background_automation, 0) FROM sessions WHERE deleted_at IS NULL"
        ).fetchall()
    finally:
        connection.close()
    return {
        str(session_id): SessionMeta(str(session_id), str(cwd), bool(background))
        for session_id, cwd, background in rows
    }


def candidate_files(root: Path, window_start: datetime) -> list[Path]:
    if not root.is_dir():
        raise RuntimeError("WorkBuddy projects directory is unavailable")
    lower_mtime = window_start.astimezone(timezone.utc).timestamp() - 86400
    result = []
    for path in root.glob("*/*.jsonl"):
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime >= lower_mtime:
                result.append(path)
        except OSError:
            continue
    return sorted(result)


def extract_text(row: dict) -> str:
    parts = []
    for item in row.get("content") or []:
        if not isinstance(item, dict) or item.get("type") not in VISIBLE_TYPES:
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    body = "\n\n".join(parts).strip()
    if row.get("role") == "user":
        matches = USER_QUERY.findall(body)
        if matches:
            body = matches[-1].strip()
        stripped = body.lstrip("\ufeff\n\r \t")
        if any(stripped.startswith(prefix) for prefix in SCAFFOLD_PREFIXES):
            return ""
    return body


def session_id_for(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = row.get("sessionId")
                if isinstance(session_id, str) and session_id:
                    return session_id
    except OSError:
        pass
    return path.stem


def inside_project(cwd: str, project_root: Path) -> bool:
    try:
        candidate = Path(cwd).resolve()
        root = project_root.resolve()
    except OSError:
        return False
    return candidate == root or root in candidate.parents


def scan(
    path: Path,
    meta: SessionMeta,
    start: datetime,
    end: datetime,
    zone: ZoneInfo,
) -> tuple[list[Message], dict]:
    messages: list[Message] = []
    invalid_rows = 0
    reasoning_rows = 0
    tool_rows = 0
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid_rows += 1
                continue
            row_type = row.get("type")
            if row_type == "reasoning":
                reasoning_rows += 1
                continue
            if row_type in {"function_call", "function_call_result"}:
                tool_rows += 1
                continue
            if row_type != "message" or row.get("role") not in {"user", "assistant"}:
                continue
            stamp = row.get("timestamp")
            if not isinstance(stamp, int):
                invalid_rows += 1
                continue
            instant = datetime.fromtimestamp(stamp / 1000, timezone.utc).astimezone(zone)
            if not start <= instant < end:
                continue
            text = extract_text(row)
            if not text:
                continue
            messages.append(
                Message(
                    timestamp=stamp,
                    local_time=instant.isoformat(),
                    session_id=meta.session_id,
                    role=row["role"],
                    text=text,
                    source_file=str(path),
                    source_line=line_number,
                    source_line_sha256=hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                )
            )
    return messages, {
        "session_id": meta.session_id,
        "source_file": str(path),
        "message_count": len(messages),
        "invalid_rows": invalid_rows,
        "reasoning_rows_excluded": reasoning_rows,
        "tool_rows_excluded": tool_rows,
    }


def deduplicate(messages: Iterable[Message]) -> list[Message]:
    seen: set[tuple[str, int, str, str]] = set()
    result = []
    for message in sorted(messages, key=lambda item: (item.timestamp, item.source_file, item.source_line)):
        digest = hashlib.sha256(message.text.encode("utf-8")).hexdigest()
        key = (message.session_id, message.timestamp, message.role, digest)
        if key not in seen:
            seen.add(key)
            result.append(message)
    return result


def write_output(
    output: Path,
    target: date,
    timezone_name: str,
    boundary: int,
    start: datetime,
    end: datetime,
    messages: list[Message],
    sessions: list[dict],
    excluded: list[dict],
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "pgh.workbuddy.l0-bundle.v1",
        "logical_date": target.isoformat(),
        "timezone": timezone_name,
        "boundary_hour": boundary,
        "window_start": start.isoformat(),
        "window_end_exclusive": end.isoformat(),
        "included_session_count": len({item.session_id for item in messages}),
        "message_count": len(messages),
        "sessions": sessions,
        "excluded_sessions": excluded,
        "policy": {
            "reasoning_included": False,
            "tool_payloads_included": False,
            "background_automation_included": False,
            "unclassified_sessions_included": False,
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for message in messages:
            handle.write(json.dumps(asdict(message), ensure_ascii=False, sort_keys=True) + "\n")
    lines = [
        "# PGH WorkBuddy L0 bundle",
        "",
        f"- Logical date: {target.isoformat()}",
        f"- Timezone: {timezone_name}",
        f"- Window: {start.isoformat()} to {end.isoformat()} (exclusive)",
        f"- Sessions: {manifest['included_session_count']}",
        f"- Messages: {len(messages)}",
        "",
    ]
    current = None
    for message in messages:
        if message.session_id != current:
            current = message.session_id
            lines.extend([f"## Session {current}", ""])
        role = "User" if message.role == "user" else "Assistant"
        lines.extend([f"### {message.local_time} · {role}", "", message.text, ""])
    (output / "transcript.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest


def main() -> int:
    args = arguments()
    timezone_name, boundary, state_scope = load_authority(args.timezone, args.boundary_hour)
    scope = args.scope or state_scope or "project"
    zone = ZoneInfo(timezone_name)
    target = date.fromisoformat(args.date)
    start = datetime.combine(target, time(hour=boundary), tzinfo=zone)
    end = start + timedelta(days=1)
    index = session_index(args.database)
    included_messages: list[Message] = []
    session_reports: list[dict] = []
    excluded: list[dict] = []

    for path in candidate_files(args.projects_root, start):
        session_id = session_id_for(path)
        meta = index.get(session_id)
        if meta is None:
            excluded.append({"session_id": session_id, "reason": "unclassified"})
            continue
        if meta.background_automation:
            excluded.append({"session_id": session_id, "reason": "background_automation"})
            continue
        if scope == "project" and not inside_project(meta.cwd, args.project_root):
            excluded.append({"session_id": session_id, "reason": "outside_project_scope"})
            continue
        messages, report = scan(path, meta, start, end, zone)
        session_reports.append(report)
        included_messages.extend(messages)

    messages = deduplicate(included_messages)
    output = args.output_dir or Path("/tmp") / "pgh-workbuddy-dream" / target.isoformat()
    manifest = write_output(
        output, target, timezone_name, boundary, start, end, messages, session_reports, excluded
    )
    print(
        json.dumps(
            {
                "logical_date": target.isoformat(),
                "output_dir": str(output),
                "sessions": manifest["included_session_count"],
                "messages": manifest["message_count"],
                "excluded_sessions": len(excluded),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"L0 extraction failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
