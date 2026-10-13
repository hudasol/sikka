"""Logging setup. Logs go to stderr and never carry record values."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, configuring the root handler once."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger("sikka")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("sikka") else f"sikka.{name}")
