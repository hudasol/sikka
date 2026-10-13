"""Canonical model and lineage. Lineage is data, not a log line."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["accepted", "repaired", "rejected"]
Decision = Literal["match", "non_match", "unresolved"]

SEVERITY_RANK = {"property_damage_only": 0, "minor_injury": 1, "serious_injury": 2, "fatal": 3}
WITHHELD = "(value withheld: personal data)"


@dataclass
class Transformation:
    """One step an adapter applied, with the value before and after."""

    step: str
    field: str
    before: Any
    after: Any
    note: str = ""


@dataclass
class SourceRef:
    producer_id: str
    file: str
    row: int
    record_id: str | None


@dataclass
class Lineage:
    sources: list[SourceRef]
    adapter: str
    adapter_version: str
    transformations: list[Transformation] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    status: Status = "accepted"
    merged_from: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProducerCrash:
    """A crash record of one producer after its adapter ran (before resolution)."""

    key: str
    producer_id: str
    occurred_ts: float | None
    lat: float | None
    lon: float | None
    segment_id: str | None
    snap_distance_m: float | None
    severity: str | None
    vehicles: int | None
    attributes: dict[str, Any]
    lineage: Lineage

    @property
    def usable(self) -> bool:
        return (
            self.lineage.status != "rejected"
            and self.occurred_ts is not None
            and (self.lat is not None and self.lon is not None)
        )


@dataclass
class CanonicalCrash:
    canonical_id: str
    occurred_at: str
    lat: float
    lon: float
    segment_id: str | None
    severity: str | None
    vehicles: int | None
    producers: list[str]
    attributes: dict[str, Any]
    lineage: Lineage
    unresolved_with: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PairDecision:
    a: str
    b: str
    score: float
    decision: Decision
    dt_min: float
    dist_m: float
    severity_agree: str
    vehicles_agree: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Exposure:
    segment_id: str
    aadt: float | None
    stations: list[str]
    valid_intervals: int
    expected_intervals: int
    lineage: Lineage

    @property
    def coverage(self) -> float:
        return self.valid_intervals / self.expected_intervals if self.expected_intervals else 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"coverage": self.coverage}
