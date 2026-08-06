#!/usr/bin/env python3
"""Fail-closed privacy and push-readiness audit for the public template."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache"}
RUNTIME_DIRS = {".pgh", "reports", "sessions", "archived_sessions", "dream-bundles"}
MAX_FILE_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = {
    "",
    ".md",
    ".py",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
    ".sh",
    ".gitignore",
}
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "example.invalid",
    "pgh.invalid",
    "users.noreply.github.com",
}
EMAIL = re.compile(r"(?<![\w.+-])([\w.+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])")
PATTERNS = {
    "absolute-home-path": re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
    "windows-home-path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s]+", re.I),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "common-token": re.compile(
        r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,})"
    ),
    "bearer-token": re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._~+/-]{16,}"),
    "internal-uri": re.compile(r"\b[a-z][a-z0-9+.-]*fs://", re.I),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I),
    "account-repository-url": re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/", re.I),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    location: str
    line: int


def text_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def external_marks(root: Path, release_mode: bool) -> list[str]:
    configured = os.environ.get("PGH_RELEASE_MARKS_FILE")
    if not configured:
        if release_mode:
            raise RuntimeError("PGH_RELEASE_MARKS_FILE is required in release mode")
        return []
    path = Path(configured).expanduser().resolve()
    if path == root or root in path.parents:
        raise RuntimeError("private marks file must live outside the release repository")
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("private marks file is missing or invalid")
    marks = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if release_mode and not marks:
        raise RuntimeError("private marks file is empty")
    return marks


def scan_text(text: str, label: str, marks: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    folded_marks = [(mark, mark.casefold()) for mark in marks]
    for line_number, line in enumerate(text.splitlines(), 1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding(name, label, line_number))
        for match in EMAIL.finditer(line):
            if match.group(2).lower() not in ALLOWED_EMAIL_DOMAINS:
                findings.append(Finding("personal-email", label, line_number))
        folded = line.casefold()
        for _mark, lowered in folded_marks:
            if lowered in folded:
                findings.append(Finding("external-private-mark", label, line_number))
    return findings


def scan_tree(root: Path, marks: list[str], release_mode: bool) -> list[Finding]:
    findings: list[Finding] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        label = relative.as_posix()
        if relative.parts and relative.parts[0] in RUNTIME_DIRS and not release_mode:
            continue
        if path.is_symlink():
            findings.append(Finding("symlink", label, 0))
            continue
        if release_mode and relative.parts and relative.parts[0] in RUNTIME_DIRS:
            findings.append(Finding("runtime-directory", label, 0))
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            findings.append(Finding("oversized-file", label, 0))
            continue
        suffix = path.suffix.lower() if path.name != ".gitignore" else ".gitignore"
        if suffix not in TEXT_SUFFIXES:
            findings.append(Finding("unexpected-binary-or-suffix", label, 0))
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding("non-utf8-text", label, 0))
            continue
        findings.extend(scan_text(body, label, marks))
    return findings


def git_output(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def scan_git(root: Path, marks: list[str], release_mode: bool) -> list[Finding]:
    if not (root / ".git").is_dir():
        if release_mode:
            return [Finding("missing-git-repository", ".git", 0)]
        return []
    findings = scan_text(
        git_output(root, ["log", "--all", "--format=fuller", "-p", "--no-color"]),
        "git-history",
        marks,
    )
    findings.extend(scan_text(git_output(root, ["remote", "-v"]), "git-remotes", marks))
    if release_mode and git_output(root, ["status", "--porcelain", "--untracked-files=all"]).strip():
        findings.append(Finding("dirty-worktree", "git-status", 0))
    return findings


def audit(root: Path, release_mode: bool) -> tuple[list[Finding], dict]:
    root = root.resolve()
    marks = external_marks(root, release_mode)
    findings = scan_tree(root, marks, release_mode)
    findings.extend(scan_git(root, marks, release_mode))
    summary = {
        "schema": "pgh.release-audit.v1",
        "release_mode": release_mode,
        "files_scanned": len(text_files(root)),
        "external_mark_count": len(marks),
        "finding_count": len(findings),
        "status": "PASS" if not findings else "FAIL",
    }
    return findings, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    release_mode = args.release or os.environ.get("PGH_RELEASE_MODE") == "1"
    try:
        findings, summary = audit(args.root, release_mode)
    except RuntimeError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for finding in findings:
        suffix = f":{finding.line}" if finding.line else ""
        print(f"{finding.rule}: {finding.location}{suffix}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
