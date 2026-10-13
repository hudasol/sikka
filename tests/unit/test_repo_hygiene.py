"""Repository wide rules from the writing and honesty standards."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sikka.core import Paths

ROOT = Paths().root
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ts", ".tsx", ".css", ".html"}
SKIP_DIRS = {".venv", "node_modules", ".git", ".sikka", ".claude", "dist", "build", ".mypy_cache"}
SKIP_DIRS |= {".pytest_cache", ".ruff_cache", ".hypothesis", "test-results", "playwright-report"}

# Built from parts so this file does not match its own patterns.
MARKER = re.compile(r"\b(" + "TO" + "DO" + "|" + "FIX" + "ME" + r")\b")
EM_DASH = chr(0x2014)
ALLOWED_EMOJI = {"\U0001f337", "\U0001f338", "\U0001f34b", "\U0001f33f"}
EMOJI = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")
AFFILIATION = re.compile(r"\b(universit(y|ies)|college|faculty of)\b", re.IGNORECASE)


def _text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            files.append(path)
    return files


FILES = _text_files()


def test_files_were_found() -> None:
    assert any(p.name == "pyproject.toml" for p in FILES)


def test_every_work_marker_is_listed_in_known_issues() -> None:
    known = (ROOT / "docs" / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
    unlisted = []
    for path in FILES:
        rel = path.relative_to(ROOT).as_posix()
        if rel == "docs/KNOWN_ISSUES.md":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MARKER.search(line) and f"{rel}:{lineno}" not in known:
                unlisted.append(f"{rel}:{lineno}")
    assert not unlisted, f"list these in docs/KNOWN_ISSUES.md: {unlisted}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_writing_rules(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert EM_DASH not in text, "em dashes are not allowed"
    stray = {c for c in EMOJI.findall(text) if c not in ALLOWED_EMOJI}
    assert not stray, f"emoji not in the allowed set: {stray}"
    if path.name != "test_repo_hygiene.py":
        assert not AFFILIATION.search(text), "no institutional affiliation may be mentioned"
