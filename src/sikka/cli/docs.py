"""Generated artefacts across layers, and their freshness check."""

from __future__ import annotations

from pathlib import Path

from sikka.conformance import render_rules_md, rules_by_field
from sikka.contract import contract_artefacts


def collect_artefacts() -> dict[str, str]:
    """Every generated text artefact, keyed by path relative to the repository root."""
    files = dict(contract_artefacts(rules_by_field()))
    files["docs/RULES.md"] = render_rules_md()
    return files


def write_artefacts(root: Path, files: dict[str, str]) -> list[str]:
    """Write files whose content differs and return their relative paths."""
    written: list[str] = []
    for rel, content in sorted(files.items()):
        path = root / rel
        if path.is_file() and path.read_bytes() == content.encode("utf-8"):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        written.append(rel)
    return written


def stale_artefacts(root: Path, files: dict[str, str]) -> list[str]:
    """Relative paths whose file on disk is missing or differs from the generator."""
    stale: list[str] = []
    for rel, content in sorted(files.items()):
        path = root / rel
        if not path.is_file() or path.read_bytes() != content.encode("utf-8"):
            stale.append(rel)
    return stale
