#!/usr/bin/env python3
"""Deterministic, local-only bootstrap for the PGH WorkBuddy template."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "runtime"
RUNTIME_WORKSPACE = RUNTIME_ROOT / "workspace"
STATE_PATH = ROOT / ".pgh" / "state.json"
RECEIPT_DIR = ROOT / ".pgh" / "receipts"
ALLOWED_EXISTING = {"BASIC_INITIALIZED", "INITIALIZED"}
REQUIRED_KEYS = {
    "confirmed",
    "user_display_name",
    "language",
    "timezone",
    "primary_use",
    "sensitive_data_boundary",
    "assistant_name",
    "assistant_role",
    "relationship",
    "style_preference",
    "current_mainline",
    "current_constraints",
    "sleep_time",
    "wake_time",
    "boundary_hour",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, payload: dict) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def one_line(value: object, label: str, maximum: int = 240) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{label} cannot be empty")
    if len(clean) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in clean):
        raise ValueError(f"{label} contains control characters")
    if "\n" in clean or "\r" in clean:
        raise ValueError(f"{label} must be one line")
    return clean.replace("`", "'")


def validate_answers(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("answers must be a JSON object")
    missing = sorted(REQUIRED_KEYS - raw.keys())
    if missing:
        raise ValueError(f"missing answers: {', '.join(missing)}")
    if raw.get("confirmed") is not True:
        raise ValueError("answers require confirmed=true")

    timezone_name = one_line(raw["timezone"], "timezone", 80)
    try:
        ZoneInfo(timezone_name)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid IANA timezone: {timezone_name}") from exc
    boundary = raw["boundary_hour"]
    if not isinstance(boundary, int) or isinstance(boundary, bool) or not 0 <= boundary <= 23:
        raise ValueError("boundary_hour must be an integer from 0 to 23")

    result = {"confirmed": True, "timezone": timezone_name, "boundary_hour": boundary}
    limits = {
        "user_display_name": 120,
        "language": 80,
        "primary_use": 240,
        "sensitive_data_boundary": 500,
        "assistant_name": 120,
        "assistant_role": 240,
        "relationship": 240,
        "style_preference": 300,
        "current_mainline": 500,
        "current_constraints": 500,
        "sleep_time": 40,
        "wake_time": 40,
    }
    for key, maximum in limits.items():
        result[key] = one_line(raw[key], key, maximum)
    return result


def interactive_answers() -> dict:
    prompts = (
        ("user_display_name", "我应该怎么称呼你："),
        ("language", "主要语言："),
        ("timezone", "IANA 时区（例如 Asia/Shanghai）："),
        ("primary_use", "主要用途（一句话）："),
        ("sensitive_data_boundary", "绝对不要写进长期记忆的信息："),
        ("assistant_name", "AI 名字："),
        ("assistant_role", "AI 身份定位："),
        ("relationship", "你希望与 AI 是什么关系："),
        ("style_preference", "表达风格偏好："),
        ("current_mainline", "最近一至三个月最重要的主线："),
        ("current_constraints", "近期约束或风险："),
        ("sleep_time", "通常几点睡："),
        ("wake_time", "通常几点起："),
    )
    values = {key: input(prompt) for key, prompt in prompts}
    values["boundary_hour"] = int(input("确认的逻辑日界线整点（0-23）：").strip())
    print("\n即将只写当前仓库中已忽略的 runtime/ 与 .pgh/。公开 workspace/ 模板保持不变。")
    values["confirmed"] = input("确认执行？输入 YES：").strip() == "YES"
    return values


def read_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state file is not a JSON object")
    return data


def replace_time_authorities(boundary: int, timezone_name: str) -> None:
    memory = RUNTIME_WORKSPACE / "MEMORY" / "00.memory_agent.md"
    body = memory.read_text(encoding="utf-8")
    body, count_memory = re.subn(
        r"物理小时 < \d{2}:00 → 逻辑日期 = 物理日期 − 1；≥ \d{2}:00 → 同物理日期",
        f"物理小时 < {boundary:02d}:00 → 逻辑日期 = 物理日期 − 1；≥ {boundary:02d}:00 → 同物理日期",
        body,
        count=1,
    )
    if count_memory != 1:
        raise RuntimeError("memory boundary authority is missing or ambiguous")
    atomic_text(memory, body)


def write_profile(a: dict) -> list[Path]:
    today = date.today().isoformat()
    iso = date.today().isocalendar()
    week = f"{iso.year}-W{iso.week:02d}"
    monday = date.today() - timedelta(days=date.today().weekday())
    sunday = monday + timedelta(days=6)
    schedule_hour = (a["boundary_hour"] + (1 if 30 >= 60 else 0)) % 24
    schedule_time = f"{schedule_hour:02d}:30"

    user = RUNTIME_WORKSPACE / "USER" / "USER.md"
    atomic_text(
        user,
        f"""---
title: 用户身份档案
type: system-instruction
priority: 0
created: {today}
updated: {today}
---

# 用户身份档案

## 核心身份

- 称呼：{a['user_display_name']}
- 主要语言：{a['language']}
- IANA 时区：{a['timezone']}
- 主要用途：{a['primary_use']}

## 隐私边界

- 不进入长期记忆：{a['sensitive_data_boundary']}
- 凭证、认证信息、私人会话原文和与当前任务无关的个人信息默认不写入。

## 系统说明

基础访谈已完成；故事访谈生成的 USER 子文件清单将在用户预览并确认后追加。

## 加载链

- 人格：`workspace/SOUL/persona/persona_SOUL.md`
- 当前处境：`workspace/Long_Term_Memory/status.md`
- 工作台：`workspace/00 Focus Zone/_current.md`
- 记忆规则：`workspace/MEMORY/00.memory_agent.md`
""",
    )

    soul = RUNTIME_WORKSPACE / "SOUL" / "persona" / "persona_SOUL.md"
    atomic_text(
        soul,
        f"""---
title: 代理人格核心
type: persona
role: {a['assistant_role']}
created: {today}
updated: {today}
---

# 代理人格核心

## 身份与关系

- AI 名字：{a['assistant_name']}
- 身份定位：{a['assistant_role']}
- 关系定位：{a['relationship']}
- 宿主：WorkBuddy

## 语气风格

- {a['style_preference']}

## 行为边界

- 不凭空补全用户身份或稳定偏好。
- 身份层变化必须经过当前用户明确确认。
- 事实、日期、版本与外部信息需要可回溯证据。
""",
    )

    status = RUNTIME_WORKSPACE / "Long_Term_Memory" / "status.md"
    atomic_text(
        status,
        f"""---
title: 当前处境
type: long-term-memory-index
status: active
created: {today}
updated: {today}
---

# 当前处境

## 当前主线

- {a['current_mainline']}

## 近期约束

- {a['current_constraints']}

## 时间感知

- IANA 时区：`{a['timezone']}`
- 通常作息：{a['sleep_time']} 入睡，{a['wake_time']} 起床
- 逻辑日界线：`{a['boundary_hour']:02d}:00`
- 每日任务建议时刻：`{schedule_time}`
- 排程状态：待 WorkBuddy 桌面端原生自动化任务回读验证

## 项目现状

故事访谈与项目导入尚未完成。
""",
    )

    current = RUNTIME_WORKSPACE / "00 Focus Zone" / "_current.md"
    atomic_text(
        current,
        f"""---
title: 当前周工作台
type: focus-week
week: "{week}"
dates: "{monday.isoformat()} ~ {sunday.isoformat()}"
status: active
created: {today}
---

# 本周

## 本周主线

- {a['current_mainline']}

## 任务清单

- [ ] 完成 PGH 故事访谈与项目导入。
- [ ] 创建并回读唯一一条 WorkBuddy 原生每日自动化任务。

## 进展记录

### {today}

- 完成基础初始化；故事访谈与排程仍待闭合。

## 风险 / 约束

- {a['current_constraints']}

## 接续断点

- 从 `CODEBUDDY.md §0 · 初始化引导` 的故事访谈继续。
""",
    )
    return [user, soul, status, current]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize(answers: dict) -> dict:
    existing = read_state()
    if existing and existing.get("status") in ALLOWED_EXISTING:
        raise RuntimeError("PGH is already initialized; refusing to overwrite local identity files")
    a = validate_answers(answers)
    if not RUNTIME_WORKSPACE.exists():
        import shutil
        shutil.copytree(ROOT / "workspace", RUNTIME_WORKSPACE)
    replace_time_authorities(a["boundary_hour"], a["timezone"])
    written = write_profile(a)
    schedule_time = f"{a['boundary_hour']:02d}:30"
    state = {
        "schema": "pgh.workbuddy.state.v1",
        "status": "BASIC_INITIALIZED",
        "story_interview_status": "PENDING",
        "schedule_status": "PENDING",
        "timezone": a["timezone"],
        "boundary_hour": a["boundary_hour"],
        "suggested_daily_time": schedule_time,
        "workbuddy_home": "<WORKBUDDY_HOME>",
        "runtime_workspace": "runtime/workspace",
        "public_template_workspace": "workspace",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    atomic_json(STATE_PATH, state)
    receipt = {
        "schema": "pgh.workbuddy.initialization-receipt.v1",
        "status": "COMMITTED",
        "created_at": now_iso(),
        "files": {str(path.relative_to(ROOT)): sha256(path) for path in written},
        "state_sha256": sha256(STATE_PATH),
        "contains_answers": False,
    }
    atomic_json(RECEIPT_DIR / "basic-initialization.json", receipt)
    return state


def complete(automation_id: str) -> dict:
    state = read_state()
    if not state or state.get("status") not in ALLOWED_EXISTING:
        raise RuntimeError("basic initialization must finish first")
    token = one_line(automation_id, "automation_id", 240)
    state.update(
        {
            "status": "INITIALIZED",
            "story_interview_status": "COMPLETED",
            "schedule_status": "ACTIVE_VERIFIED",
            "automation_id": token,
            "updated_at": now_iso(),
        }
    )
    atomic_json(STATE_PATH, state)
    atomic_json(
        RECEIPT_DIR / "completed-initialization.json",
        {
            "schema": "pgh.workbuddy.completion-receipt.v1",
            "status": "COMMITTED",
            "created_at": now_iso(),
            "automation_id_present": True,
            "state_sha256": sha256(STATE_PATH),
            "claim_boundary": "automation must have been read back in WorkBuddy before this command",
        },
    )
    return state


def public_status(state: dict | None) -> dict:
    if not state:
        return {"status": "UNINITIALIZED"}
    return {
        key: state.get(key)
        for key in (
            "schema",
            "status",
            "story_interview_status",
            "schedule_status",
            "timezone",
            "boundary_hour",
            "suggested_daily_time",
            "created_at",
            "updated_at",
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--interactive", action="store_true")
    mode.add_argument("--answers-file", type=Path)
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--complete", action="store_true")
    parser.add_argument("--automation-id")
    args = parser.parse_args()

    if args.status:
        result = read_state()
    elif args.complete:
        if not args.automation_id:
            parser.error("--complete requires --automation-id after WorkBuddy readback")
        result = complete(args.automation_id)
    else:
        if args.interactive:
            raw = interactive_answers()
        else:
            raw = json.loads(args.answers_file.read_text(encoding="utf-8"))
        result = initialize(raw)
    print(json.dumps(public_status(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
