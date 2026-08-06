#!/usr/bin/env python3
"""Run all repository tests and the privacy boundary audit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], env: dict[str, str] | None = None) -> int:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    if run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]):
        return 1
    env = os.environ.copy()
    command = [sys.executable, "scripts/release_audit.py"]
    if args.release:
        env["PGH_RELEASE_MODE"] = "1"
        command.append("--release")
    return run(command, env)


if __name__ == "__main__":
    raise SystemExit(main())
