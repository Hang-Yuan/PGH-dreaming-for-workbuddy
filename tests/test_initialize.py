from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def answers() -> dict:
    return {
        "confirmed": True,
        "user_display_name": "Example User",
        "language": "中文",
        "timezone": "UTC",
        "primary_use": "research and writing",
        "sensitive_data_boundary": "credentials and private correspondence",
        "assistant_name": "Example Assistant",
        "assistant_role": "long-term collaborator",
        "relationship": "thought partner",
        "style_preference": "direct and concise",
        "current_mainline": "initialize a local knowledge workspace",
        "current_constraints": "keep all personal data local",
        "sleep_time": "23:00",
        "wake_time": "07:00",
        "boundary_hour": 4,
    }


class InitializeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.copy = Path(self.temporary.name) / "repo"
        shutil.copytree(
            ROOT,
            self.copy,
            ignore=shutil.ignore_patterns(".git", ".pgh", "__pycache__"),
        )
        self.input = Path(self.temporary.name) / "answers.json"
        self.input.write_text(json.dumps(answers()), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def run_init(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/initialize.py", *arguments],
            cwd=self.copy,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_basic_initialization_is_committed_and_local(self):
        result = self.run_init("--answers-file", str(self.input))
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.copy / ".pgh" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "BASIC_INITIALIZED")
        self.assertEqual(state["schedule_status"], "PENDING")
        user = (self.copy / "runtime" / "workspace" / "USER" / "USER.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Example User", user)
        self.assertNotIn("[用户称呼]", user)
        public_user = (self.copy / "workspace" / "USER" / "USER.md").read_text(encoding="utf-8")
        self.assertIn("[用户称呼]", public_user)
        codebuddy = (self.copy / "CODEBUDDY.md").read_text(encoding="utf-8")
        self.assertIn("模板逻辑日期口径", codebuddy)
        runtime_memory = (
            self.copy / "runtime" / "workspace" / "MEMORY" / "00.memory_agent.md"
        ).read_text(encoding="utf-8")
        self.assertIn("物理小时 < 04:00", runtime_memory)
        receipt = json.loads(
            (self.copy / ".pgh" / "receipts" / "basic-initialization.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(receipt["status"], "COMMITTED")
        self.assertFalse(receipt["contains_answers"])

    def test_second_initialization_refuses_overwrite(self):
        first = self.run_init("--answers-file", str(self.input))
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_init("--answers-file", str(self.input))
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("refusing to overwrite", second.stderr)

    def test_completion_requires_verified_automation_id(self):
        first = self.run_init("--answers-file", str(self.input))
        self.assertEqual(first.returncode, 0, first.stderr)
        missing = self.run_init("--complete")
        self.assertNotEqual(missing.returncode, 0)
        complete = self.run_init("--complete", "--automation-id", "example-automation")
        self.assertEqual(complete.returncode, 0, complete.stderr)
        state = json.loads((self.copy / ".pgh" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "INITIALIZED")
        self.assertEqual(state["schedule_status"], "ACTIVE_VERIFIED")

    def test_invalid_timezone_fails_without_state(self):
        invalid = answers()
        invalid["timezone"] = "Not/A_Zone"
        self.input.write_text(json.dumps(invalid), encoding="utf-8")
        result = self.run_init("--answers-file", str(self.input))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.copy / ".pgh" / "state.json").exists())

    def test_uninitialized_status_is_minimal(self):
        result = self.run_init("--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "UNINITIALIZED"})


if __name__ == "__main__":
    unittest.main()
