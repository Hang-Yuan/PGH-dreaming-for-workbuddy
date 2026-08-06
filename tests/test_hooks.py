from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codebuddy" / "hooks" / "runtime_context.py"


class HookTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, event: str, payload: dict) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["CODEBUDDY_PROJECT_DIR"] = str(self.project)
        return subprocess.run(
            [sys.executable, str(HOOK), "--event", event],
            input=json.dumps(payload),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )

    def test_uninitialized_context_contains_only_bootstrap_instruction(self):
        result = self.invoke(
            "SessionStart", {"hook_event_name": "SessionStart", "source": "startup"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("PGH_INIT_REQUIRED", context)
        self.assertNotIn("persona_SOUL", context)

    def test_initialized_context_reads_only_expected_identity_files(self):
        (self.project / ".pgh").mkdir()
        (self.project / ".pgh" / "state.json").write_text(
            json.dumps(
                {
                    "status": "BASIC_INITIALIZED",
                    "schedule_status": "PENDING",
                    "runtime_workspace": "runtime/workspace",
                }
            ),
            encoding="utf-8",
        )
        soul = self.project / "runtime" / "workspace" / "SOUL" / "persona"
        user = self.project / "runtime" / "workspace" / "USER"
        soul.mkdir(parents=True)
        user.mkdir(parents=True)
        (soul / "persona_SOUL.md").write_text("assistant identity", encoding="utf-8")
        (user / "USER.md").write_text("user identity", encoding="utf-8")
        result = self.invoke("UserPromptSubmit", {"hook_event_name": "UserPromptSubmit"})
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("assistant identity", context)
        self.assertIn("user identity", context)
        self.assertIn("schedule_status=PENDING", context)

    def test_wrong_event_fails_closed(self):
        result = self.invoke("UserPromptSubmit", {"hook_event_name": "SessionStart"})
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
