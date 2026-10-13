"""Rule registry. Each rule is a small declarative object with a check function."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

if TYPE_CHECKING:
    from sikka.conformance.context import RuleContext

Family = Literal["S", "V", "R", "X", "T", "P"]
Severity = Literal["error", "warning", "info"]
Scope = Literal["record", "series", "file"]

FAMILY_NAMES: dict[str, str] = {
    "S": "Structural",
    "V": "Semantic",
    "R": "Referential",
    "X": "Cross feed",
    "T": "Timeliness and completeness",
    "P": "Privacy",
}
FINDING_COLUMNS = ["_row", "series", "field", "detail"]


def findings(rows: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Build a findings frame with the standard columns."""
    frame = pd.DataFrame(rows or [], columns=FINDING_COLUMNS)
    frame["_row"] = frame["_row"].astype("Int64")
    return frame


@dataclass(frozen=True)
class Example:
    """A failing and a passing record, documented in RULES.md and used in tests."""

    feed_type: str
    failing: dict[str, Any]
    passing: dict[str, Any]
    header: dict[str, Any] | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    family: Family
    title: str
    severity: Severity
    description: str
    rationale: str
    fix_hint: str
    feed_types: tuple[str, ...]
    fields: tuple[str, ...]
    scope: Scope
    check: Callable[[RuleContext], pd.DataFrame]
    example: Example | None = None
    needs: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "family_name": FAMILY_NAMES[self.family],
            "title": self.title,
            "severity": self.severity,
            "description": self.description,
            "rationale": self.rationale,
            "fix_hint": self.fix_hint,
            "feed_types": list(self.feed_types),
            "fields": list(self.fields),
            "scope": self.scope,
            "needs": list(self.needs),
        }


REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.id in REGISTRY:
        raise ValueError(f"duplicate rule id {rule.id}")
    REGISTRY[rule.id] = rule
    return rule


def rules_for(feed_type: str | None) -> list[Rule]:
    return [
        r
        for r in sorted(REGISTRY.values(), key=lambda r: r.id)
        if feed_type is None or feed_type in r.feed_types or not r.feed_types
    ]
