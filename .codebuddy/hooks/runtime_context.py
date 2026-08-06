#!/usr/bin/env python3
"""Inject PGH initialization or local identity context into WorkBuddy hooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_INPUT_BYTES = 256 * 1024
MAX_IDENTITY_BYTES = 1024 * 1024
SESSION_SOURCES = {"startup", "resume", "clear", "compact", "fork"}
VALID_STATUS = {"BASIC_INITIALIZED", "INITIALIZED"}


def project_root() -> Path:
    configured = os.environ.get("CODEBUDDY_PROJECT_DIR")
    root = Path(configured) if configured else Path(__file__).resolve().parents[2]
    return root.resolve()


def parse_payload(event: str) -> dict:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise SystemExit("hook input exceeds 256 KiB")
    if not raw.strip():
        payload: dict = {}
    else:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid hook JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("hook payload must be a JSON object")
    actual = payload.get("hook_event_name")
    if actual not in (None, event):
        raise SystemExit(f"unexpected hook event: {actual}")
    if event == "SessionStart":
        source = payload.get("source", "startup")
        if source not in SESSION_SOURCES:
            raise SystemExit(f"unsupported SessionStart source: {source}")
    return payload


def read_state(root: Path) -> dict | None:
    path = root / ".pgh" / "state.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise SystemExit("invalid PGH state file")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid PGH state JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit("PGH state must be a JSON object")
    return state


def identity_section(root: Path, relative: str) -> str:
    path = (root / relative).resolve()
    if root not in path.parents or path.is_symlink() or not path.is_file():
        raise SystemExit(f"invalid identity source: {relative}")
    if path.stat().st_size > MAX_IDENTITY_BYTES:
        raise SystemExit(f"identity source exceeds 1 MiB: {relative}")
    text = path.read_text(encoding="utf-8").rstrip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"--- BEGIN {relative} sha256={digest} ---\n{text}\n--- END {relative} ---"


def context(root: Path, event: str, payload: dict) -> str:
    state = read_state(root)
    if state is None or state.get("status") not in VALID_STATUS:
        return (
            "PGH_INIT_REQUIRED\n"
            "This project has not completed basic initialization. "
            "Invoke the initialize-pgh skill before ordinary work. "
            "Do not infer user identity, copy data from unrelated directories, "
            "or claim that persistent scheduling is active.\n"
        )

    workspace = state.get("runtime_workspace", "runtime/workspace")
    if not isinstance(workspace, str) or Path(workspace).is_absolute() or ".." in Path(workspace).parts:
        raise SystemExit("invalid runtime workspace in PGH state")
    timezone_name = state.get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name or len(timezone_name) > 80:
        raise SystemExit("invalid timezone in PGH state")
    try:
        ZoneInfo(timezone_name)
    except (KeyError, ValueError) as exc:
        raise SystemExit("invalid timezone in PGH state") from exc
    boundary = state.get("boundary_hour")
    if not isinstance(boundary, int) or isinstance(boundary, bool) or not 0 <= boundary <= 23:
        raise SystemExit("invalid logical-day boundary in PGH state")
    availability = state.get("night_runtime_availability", "未记录；初始化尚未闭合")
    if (
        not isinstance(availability, str)
        or not availability.strip()
        or len(availability) > 300
        or any(ord(char) < 32 or ord(char) == 127 for char in availability)
    ):
        raise SystemExit("invalid night runtime availability in PGH state")
    source = payload.get("source", "prompt")
    sections = [
        f"PGH_WORKBUDDY_CONTEXT_V1 event={event} source={source}",
        f"initialization_status={state['status']}",
        f"schedule_status={state.get('schedule_status', 'UNKNOWN')}",
        f"runtime_workspace={workspace}",
        f"timezone={timezone_name}",
        f"logical_day_boundary={boundary:02d}:00",
        f"daily_schedule_time={boundary:02d}:30",
        f"night_runtime_availability={availability.strip()}",
        identity_section(root, f"{workspace}/SOUL/persona/persona_SOUL.md"),
        identity_section(root, f"{workspace}/USER/USER.md"),
    ]
    return "\n".join(sections) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=("SessionStart", "UserPromptSubmit"), required=True)
    args = parser.parse_args()
    payload = parse_payload(args.event)
    body = context(project_root(), args.event, payload)
    print(
        json.dumps(
            {
                "continue": True,
                "suppressOutput": True,
                "hookSpecificOutput": {
                    "hookEventName": args.event,
                    "additionalContext": body,
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
