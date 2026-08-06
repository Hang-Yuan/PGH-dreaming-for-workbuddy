from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


class WorkBuddyStructureTest(unittest.TestCase):
    def test_project_entrypoints_exist(self):
        self.assertTrue((ROOT / "CODEBUDDY.md").is_file())
        self.assertTrue((ROOT / ".codebuddy" / "settings.json").is_file())
        self.assertTrue((ROOT / ".codebuddy" / "skills" / "initialize-pgh" / "SKILL.md").is_file())

    def test_agents_use_official_markdown_format(self):
        directory = ROOT / ".codebuddy" / "agents"
        self.assertEqual(list(directory.glob("*.toml")), [])
        agents = sorted(directory.glob("*.md"))
        self.assertEqual(len(agents), 2)
        for path in agents:
            body = path.read_text(encoding="utf-8")
            self.assertTrue(body.startswith("---\n"), path)
            self.assertIn("model: inherit", body)

    def test_hooks_use_python_and_project_root(self):
        settings = json.loads((ROOT / ".codebuddy" / "settings.json").read_text(encoding="utf-8"))
        commands = [
            hook["command"]
            for matchers in settings["hooks"].values()
            for matcher in matchers
            for hook in matcher["hooks"]
        ]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(command.startswith("python3 ") for command in commands))
        self.assertTrue(all("$CODEBUDDY_PROJECT_DIR" in command for command in commands))

    def test_no_retired_runtime_tree(self):
        self.assertFalse((ROOT / ".codebuddy" / "skills" / "_retired_20260801").exists())
        self.assertFalse((ROOT / "reports").exists())

    def test_readme_has_download_to_initialize_path(self):
        body = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("开始初始化 PGH", body)
        self.assertIn("python3 scripts/initialize.py --interactive", body)
        self.assertIn("PGH_RELEASE_MARKS_FILE", body)
        self.assertNotIn("github.com/", body)

    def test_daily_extractor_uses_repository_scope(self):
        body = (
            ROOT / ".codebuddy" / "skills" / "daily-dream" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("--project-root .", body)
        self.assertIn("--output-dir runtime/dream-bundles/YYYY-MM-DD", body)
        self.assertNotIn("--project-root <WORKSPACE_ROOT>", body)

    def test_core_schedule_contract_matches_all_hosts(self):
        root = (ROOT / "CODEBUDDY.md").read_text(encoding="utf-8")
        schedule = (ROOT / "docs" / "schedule_interview.md").read_text(encoding="utf-8")
        daily = (
            ROOT / ".codebuddy" / "skills" / "daily-dream" / "SKILL.md"
        ).read_text(encoding="utf-8")
        week_sync = (
            ROOT / ".codebuddy" / "skills" / "week-sync" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for expected in ("作息", "IANA 时区", "WorkBuddy 可用性"):
            self.assertIn(expected, root)
            self.assertIn(expected, schedule)
        self.assertIn("日界线后 30 分钟", schedule)
        self.assertIn("唯一一条 `daily-dream`", root)
        self.assertIn("A 段 · 工作固化", daily)
        self.assertIn("B 段 · 记忆代谢", daily)
        self.assertIn("weekly-dream", daily)
        self.assertIn("dream_receipts/YYYY-MM-DD.json", daily)
        self.assertIn("最近三个", week_sync)

    def test_no_stale_workbuddy_adapter_routes(self):
        active = [
            ROOT / "CODEBUDDY.md",
            ROOT / "docs" / "核心分流.md",
            ROOT / ".codebuddy" / "rules" / "pgh-core.md",
            ROOT / ".codebuddy" / "rules" / "workbuddy-adapter.md",
            ROOT / "workspace" / "MEMORY" / "00.memory_agent.md",
        ]
        body = "\n".join(path.read_text(encoding="utf-8") for path in active)
        self.assertNotIn("<WORKBUDDY_HOME>/skills/", body)
        self.assertNotIn("config.toml", body)
        self.assertNotIn("当前实验区", body)
        self.assertNotIn("PGH Core 规则（脱敏实验版）", body)

    def test_common_core_skill_set_is_complete(self):
        expected = {
            "close-node",
            "create-project",
            "daily-dream",
            "new-file",
            "quarterly-archive",
            "week-sync",
            "weekly-dream",
            "write-progress",
        }
        actual = {
            path.parent.name
            for path in (ROOT / ".codebuddy" / "skills").glob("*/SKILL.md")
        }
        self.assertTrue(expected.issubset(actual))
        self.assertEqual(actual - expected, {"initialize-pgh"})

    def test_local_markdown_links_resolve(self):
        failures = []
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for path in ROOT.rglob("*.md"):
            if ".git" in path.parts:
                continue
            for target in pattern.findall(path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                clean = unquote(target.split("#", 1)[0])
                if clean and not (path.parent / clean).resolve().exists():
                    failures.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
