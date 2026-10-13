"""Configuration and repository paths."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from ``start`` to the directory holding ``pyproject.toml``.

    ``SIKKA_ROOT`` overrides the search, which keeps installed copies usable.
    """
    env = os.environ.get("SIKKA_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "sikka").is_dir():
            return candidate
    return here


@dataclass(frozen=True)
class Paths:
    """Well known locations inside the repository."""

    root: Path = field(default_factory=find_repo_root)

    @property
    def contract(self) -> Path:
        return self.root / "contract"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def samples(self) -> Path:
        return self.root / "data" / "samples"

    @property
    def build(self) -> Path:
        """Ignored working directory for large generated outputs."""
        return self.root / "build"

    @property
    def web(self) -> Path:
        return self.root / "web"


DEFAULT_SEED = 20260422
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
