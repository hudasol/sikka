"""Generated artefacts across layers, and their freshness check."""

from __future__ import annotations

from pathlib import Path

from sikka.contract import contract_artefacts


def rules_by_field() -> dict[str, list[str]]:
    """Map ``feed.field`` to rule ids. Filled in once the rule registry exists."""
    return {}


def collect_artefacts() -> dict[str, str]:
    """Every generated text artefact, keyed by path relative to the repository root."""
    return dict(contract_artefacts(rules_by_field()))


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
