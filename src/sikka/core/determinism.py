"""Determinism helpers.

Every stochastic step in Sikka takes an explicit integer seed. Independent
streams are derived from that seed with a stable name, so adding a new stream
never shifts the numbers produced by an existing one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


def _stream_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def rng(seed: int, *stream: str) -> np.random.Generator:
    """Return a generator for ``seed`` and a named stream path.

    The same seed and stream path always give the same sequence on every
    platform, because the stream key is a SHA 256 digest rather than Python's
    salted ``hash``.
    """
    if seed < 0:
        raise ValueError("seed must be a non negative integer")
    keys = [_stream_key(part) for part in stream]
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, *keys])))


def stable_json_dumps(value: Any, *, indent: int | None = None) -> str:
    """Serialise to JSON with sorted keys and no platform dependent spacing."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        indent=indent,
        separators=(",", ":") if indent is None else (",", ": "),
        allow_nan=False,
    )


def round_floats(value: Any, digits: int = 6) -> Any:
    """Round every float in a nested structure so outputs are byte stable."""
    if isinstance(value, float):
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        return {k: round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [round_floats(v, digits) for v in value]
    return value


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF 8 text with LF line endings on every platform."""
    path.write_bytes(text.encode("utf-8"))
