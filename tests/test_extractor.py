from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / ".codebuddy" / "skills" / "daily-dream" / "scripts" / "extract_daily_transcripts.py"


class ExtractorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.projects = base / "projects"
        self.projects.mkdir()
        self.project_root = base / "pgh-project"
        self.project_root.mkdir()
        self.database = base / "workbuddy.db"
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT NOT NULL, "
            "is_background_automation INTEGER, deleted_at INTEGER)"
        )
        rows = [
            ("human-session", str(self.project_root), 0, None),
            ("automation-session", str(self.project_root), 1, None),
            ("outside-session", str(base / "another-project"), 0, None),
        ]
        connection.executemany("INSERT INTO sessions VALUES (?, ?, ?, ?)", rows)
        connection.commit()
        connection.close()
        stamp = int(datetime(2026, 1, 2, 12, tzinfo=timezone.utc).timestamp() * 1000)
        self.write_session(
            "human-session",
            [
                self.message("human-session", stamp, "user", "hello from user"),
                {"type": "reasoning", "timestamp": stamp, "rawContent": "hidden reasoning"},
                self.message("human-session", stamp + 1, "assistant", "hello from assistant"),
            ],
        )
        self.write_session(
            "automation-session",
            [self.message("automation-session", stamp, "assistant", "automation output")],
        )
        self.write_session(
            "outside-session",
            [self.message("outside-session", stamp, "user", "outside output")],
        )
        self.write_session(
            "unclassified-session",
            [self.message("unclassified-session", stamp, "user", "unclassified output")],
        )
        self.output = base / "output"

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def message(session: str, stamp: int, role: str, text: str) -> dict:
        part_type = "input_text" if role == "user" else "output_text"
        return {
            "type": "message",
            "sessionId": session,
            "timestamp": stamp,
            "role": role,
            "content": [{"type": part_type, "text": text}],
        }

    def write_session(self, session: str, rows: list[dict]) -> None:
        directory = self.projects / "project-key"
        directory.mkdir(exist_ok=True)
        with (directory / f"{session}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def run_extractor(self, database: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(EXTRACTOR),
                "--date",
                "2026-01-02",
                "--timezone",
                "UTC",
                "--boundary-hour",
                "4",
                "--projects-root",
                str(self.projects),
                "--database",
                str(database or self.database),
                "--project-root",
                str(self.project_root),
                "--output-dir",
                str(self.output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_excludes_automation_outside_and_unclassified_sessions(self):
        result = self.run_extractor()
        self.assertEqual(result.returncode, 0, result.stderr)
        transcript = (self.output / "transcript.md").read_text(encoding="utf-8")
        self.assertIn("hello from user", transcript)
        self.assertIn("hello from assistant", transcript)
        self.assertNotIn("automation output", transcript)
        self.assertNotIn("outside output", transcript)
        self.assertNotIn("unclassified output", transcript)
        self.assertNotIn("hidden reasoning", transcript)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        reasons = {item["reason"] for item in manifest["excluded_sessions"]}
        self.assertEqual(reasons, {"background_automation", "outside_project_scope", "unclassified"})
        self.assertFalse(manifest["policy"]["background_automation_included"])

    def test_missing_session_index_fails_closed(self):
        result = self.run_extractor(Path(self.temporary.name) / "missing.db")
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing unclassified", result.stderr)


if __name__ == "__main__":
    unittest.main()
