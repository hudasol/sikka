"""Identifier conventions shared by every layer."""

from __future__ import annotations

import hashlib
import re

ID_PATTERN = r"^[A-Z0-9_\-]{3,40}$"
_ID_RE = re.compile(ID_PATTERN)


def is_valid_id(value: str) -> bool:
    """True when ``value`` is an opaque contract identifier."""
    return bool(_ID_RE.match(value))


def content_hash(data: bytes, *, length: int = 16) -> str:
    """Short, stable, upper case hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()[:length].upper()


def make_id(prefix: str, *parts: str, length: int = 12) -> str:
    """Build a deterministic identifier from a prefix and a list of parts."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:length].upper()
    ident = f"{prefix}-{digest}"
    if not is_valid_id(ident):
        raise ValueError(f"generated identifier does not match the contract pattern: {ident}")
    return ident
