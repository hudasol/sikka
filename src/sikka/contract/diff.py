"""Compare two contract versions and classify each change.

Compatibility rule (see ``contract/CHANGELOG.md``): adding an optional field
is a minor change; adding a required field, removing a field or changing the
type, unit, allowed values or meaning of a field is a major change; wording
changes to descriptions are patch changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from sikka.contract.schema import FieldSpec, field_specs, version_schemas
from sikka.contract.versions import ContractVersion

Impact = Literal["major", "minor", "patch"]
_ORDER = {"patch": 0, "minor": 1, "major": 2}


@dataclass(frozen=True)
class Change:
    feed: str
    field: str
    kind: Literal["added", "removed", "changed"]
    impact: Impact
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ContractDiff:
    old: str
    new: str
    changes: list[Change]

    @property
    def required_bump(self) -> Impact | None:
        if not self.changes:
            return None
        return max((c.impact for c in self.changes), key=_ORDER.__getitem__)

    @property
    def declared_bump(self) -> Impact | None:
        old = [int(p) for p in self.old.split(".")]
        new = [int(p) for p in self.new.split(".")]
        if new[0] != old[0]:
            return "major"
        if new[1] != old[1]:
            return "minor"
        if new[2] != old[2]:
            return "patch"
        return None

    @property
    def compatible(self) -> bool:
        """True when the declared version bump is at least the required one."""
        required = self.required_bump
        if required is None:
            return True
        declared = self.declared_bump
        return declared is not None and _ORDER[declared] >= _ORDER[required]

    def as_dict(self) -> dict[str, Any]:
        return {
            "old": self.old,
            "new": self.new,
            "required_bump": self.required_bump,
            "declared_bump": self.declared_bump,
            "compatible": self.compatible,
            "changes": [c.as_dict() for c in self.changes],
        }


def _specs(version: ContractVersion) -> dict[tuple[str, str], FieldSpec]:
    out: dict[tuple[str, str], FieldSpec] = {}
    for feed, schema in version_schemas(version).items():
        for spec in field_specs(schema, feed):
            out[(feed, spec.name)] = spec
    return out


def diff_versions(old: ContractVersion, new: ContractVersion) -> ContractDiff:
    a, b = _specs(old), _specs(new)
    changes: list[Change] = []
    for key in sorted(set(a) | set(b)):
        feed, name = key
        if key not in a:
            spec = b[key]
            impact: Impact = "minor" if not spec.required else "major"
            req = "required" if spec.required else "optional"
            changes.append(Change(feed, name, "added", impact, f"new {req} {spec.type} field"))
            continue
        if key not in b:
            changes.append(Change(feed, name, "removed", "major", "field removed"))
            continue
        before, after = a[key], b[key]
        semantic = ("type", "unit", "allowed", "pattern", "required")
        for attr in semantic:
            old_v, new_v = getattr(before, attr), getattr(after, attr)
            if old_v != new_v:
                changes.append(
                    Change(feed, name, "changed", "major", f"{attr}: {old_v!r} -> {new_v!r}")
                )
        for attr in ("description_en", "description_ar"):
            if getattr(before, attr) != getattr(after, attr):
                changes.append(Change(feed, name, "changed", "patch", f"{attr} reworded"))
    return ContractDiff(old.version, new.version, changes)


def render_diff_text(diff: ContractDiff) -> str:
    lines = [f"Contract diff {diff.old} -> {diff.new}"]
    if not diff.changes:
        lines.append("No changes.")
    for c in diff.changes:
        lines.append(f"  [{c.impact}] {c.kind:<8} {c.feed}.{c.field}: {c.detail}")
    lines.append(f"Required bump: {diff.required_bump or 'none'}")
    lines.append(f"Declared bump: {diff.declared_bump or 'none'}")
    lines.append(f"Compatible with the versioning rule: {'yes' if diff.compatible else 'no'}")
    return "\n".join(lines)
