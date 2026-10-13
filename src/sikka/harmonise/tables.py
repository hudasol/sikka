"""Adapter mapping tables, one per producer. These are data, not code paths.

Each table states the producer's own conventions inside the contract (identifier
style, which optional fields it fills) and how known deviations are mapped back.
Record level repairs are triggered by conformance findings, so the same table
works whether a deviation is systematic or occasional.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ADAPTER_VERSION = "1.0.0"

# Contract severities map to themselves. The legacy numeric scale (seen as fault
# F05) is mapped conservatively: code 2 mixes serious and minor injuries, so it is
# mapped to minor_injury and marked lossy in the lineage.
SEVERITY_CONTRACT = {
    "fatal": "fatal",
    "serious_injury": "serious_injury",
    "minor_injury": "minor_injury",
    "property_damage_only": "property_damage_only",
}
SEVERITY_LEGACY = {"1": "fatal", "2": "minor_injury", "3": "property_damage_only"}
LOSSY_LEGACY = {"2"}

FIELD_ALIASES = {"occurred_time": "occurred_at", "veh_count": "vehicle_count"}
SEGMENT_PREFIX_ALIASES = {"S": "SEG"}
SEGMENT_NUMBER_WIDTH = 3


@dataclass(frozen=True)
class AdapterTable:
    producer_id: str
    role: str
    crash_id_pattern: str
    fills_segment_ref: bool
    fills_direction: bool
    resolution_priority: int
    severity_authority: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def adapter_id(self) -> str:
        return f"adapter-{self.producer_id.lower().replace('_', '-')}"


ADAPTERS: dict[str, AdapterTable] = {
    "PRODUCER_A": AdapterTable(
        producer_id="PRODUCER_A",
        role="road authority",
        crash_id_pattern=r"^A-\d{4}-\d{6}$",
        fills_segment_ref=True,
        fills_direction=True,
        resolution_priority=2,
        notes=("Reports crashes on its own corridors only.",),
    ),
    "PRODUCER_B": AdapterTable(
        producer_id="PRODUCER_B",
        role="police",
        crash_id_pattern=r"^PB-\d{7}$",
        fills_segment_ref=True,
        fills_direction=True,
        resolution_priority=1,
        notes=("Widest coverage; first choice for location and time.",),
    ),
    "PRODUCER_C": AdapterTable(
        producer_id="PRODUCER_C",
        role="emirate level authority",
        crash_id_pattern=r"^C_\d{8}_\d{4}$",
        fills_segment_ref=True,
        fills_direction=True,
        resolution_priority=3,
        notes=("Reports crashes on its own corridors only; sends CSV.",),
    ),
    "PRODUCER_D": AdapterTable(
        producer_id="PRODUCER_D",
        role="health sector crash reporting",
        crash_id_pattern=r"^HD-\d{6}$",
        fills_segment_ref=False,
        fills_direction=False,
        resolution_priority=4,
        severity_authority=True,
        notes=(
            "Fatal and serious crashes only; no segment references.",
            "Treated as the authority on injury severity when it reports a crash.",
        ),
    ),
}

DEFAULT_ADAPTER = AdapterTable("UNKNOWN", "unknown producer", r"^.+$", True, True, 9)


def table_for(producer_id: str | None) -> AdapterTable:
    return ADAPTERS.get(producer_id or "", DEFAULT_ADAPTER)
