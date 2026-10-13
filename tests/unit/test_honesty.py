"""Honesty rules: real entities only in CONTEXT.md, docs agree with the code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sikka.conformance import REGISTRY
from sikka.core import Paths
from sikka.synth import CATALOGUE

ROOT = Paths().root
# Names of real bodies and sources that may appear in docs/CONTEXT.md only.
REAL_ENTITIES = [
    "Gulf News",
    "Gulf Today",
    "gulfnews",
    "gulftoday",
    "Federal National Council",
    "Ministry",
    "RTA",
    "Abu Dhabi Police",
    "Dubai Police",
    "Etihad Rail",
]
SKIP = {".venv", "node_modules", ".git", ".sikka", ".claude", "dist", "build", "test-results"}
SUFFIXES = {".py", ".md", ".ts", ".tsx", ".json", ".css", ".html", ".toml", ".yml"}


def _files() -> list[Path]:
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in SUFFIXES
        and not any(part in SKIP for part in p.relative_to(ROOT).parts)
    ]


def test_real_entities_only_in_context() -> None:
    allowed = {ROOT / "docs" / "CONTEXT.md", Path(__file__).resolve()}
    offenders = []
    for path in _files():
        if path.resolve() in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in REAL_ENTITIES:
            if re.search(rf"\b{re.escape(name)}\b", text):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {name}")
    assert not offenders, offenders


@pytest.mark.parametrize("doc", ["README.md", "docs/METHOD.md", "docs/ARCHITECTURE.md"])
def test_rule_count_in_docs_matches_registry(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    counts = {int(n) for n in re.findall(r"\b(\d+) (?:explained )?(?:rules|checks)\b", text)}
    assert counts <= {len(REGISTRY)}, (doc, counts)


def test_fault_count_matches_catalogue() -> None:
    assert len(CATALOGUE) == 25


def test_required_docs_exist() -> None:
    for name in (
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/METHOD.md",
        "docs/LIMITATIONS.md",
        "docs/PILOT.md",
        "docs/SECURITY.md",
        "docs/DATA_STATEMENT.md",
        "docs/CONTEXT.md",
        "docs/PREREGISTRATION.md",
    ):
        assert (ROOT / name).is_file(), name


def test_every_adr_has_a_status() -> None:
    adrs = sorted((ROOT / "docs" / "adr").glob("*.md"))
    assert len(adrs) >= 8
    for adr in adrs:
        assert "Status: accepted" in adr.read_text(encoding="utf-8"), adr.name
