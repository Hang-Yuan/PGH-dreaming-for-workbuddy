from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_audit", ROOT / "scripts" / "release_audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReleaseAuditTest(unittest.TestCase):
    def test_release_mode_requires_external_marks(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                MODULE.external_marks(ROOT, True)

    def test_empty_external_marks_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            marks = Path(temporary) / "marks.txt"
            marks.write_text("# comments only\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PGH_RELEASE_MARKS_FILE": str(marks)}, clear=True):
                with self.assertRaises(RuntimeError):
                    MODULE.external_marks(ROOT, True)

    def test_external_mark_is_detected_without_echoing_value(self):
        findings = MODULE.scan_text("prefix publisher-secret-name suffix", "sample", ["publisher-secret-name"])
        self.assertEqual([item.rule for item in findings], ["external-private-mark"])

    def test_absolute_home_and_personal_email_are_detected(self):
        home_path = "/" + "Users/" + "private-person/project"
        address = "person" + "@" + "private.test"
        findings = MODULE.scan_text(f"{home_path}\n{address}", "sample", [])
        self.assertEqual({item.rule for item in findings}, {"absolute-home-path", "personal-email"})

    def test_reserved_email_domain_is_allowed(self):
        findings = MODULE.scan_text("maintainers" + "@" + "pgh.invalid", "sample", [])
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
