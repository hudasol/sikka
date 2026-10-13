"""Adapters: small functions that apply the mapping tables to one record.

Every change is recorded as a Transformation with its before and after value,
except values of personal fields, which are never retained.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sikka.contract import UAE_BBOX, is_prohibited_field
from sikka.core import format_utc, is_utc_z, parse_utc
from sikka.harmonise.model import WITHHELD, Lineage, SourceRef, Transformation
from sikka.harmonise.tables import (
    ADAPTER_VERSION,
    FIELD_ALIASES,
    LOSSY_LEGACY,
    SEGMENT_NUMBER_WIDTH,
    SEGMENT_PREFIX_ALIASES,
    SEVERITY_CONTRACT,
    SEVERITY_LEGACY,
    table_for,
)

ASCII_DIGITS = str.maketrans(
    "".join(chr(0x0660 + i) for i in range(10)) + "".join(chr(0x06F0 + i) for i in range(10)),
    "0123456789" * 2,
)
LOCAL_OFFSET = timedelta(hours=4)
_SEGMENT = re.compile(r"^([A-Za-z]+)-([A-Za-z]+)-0*(\d+)$")


def new_lineage(producer: str | None, file: str, row: int, record_id: str | None) -> Lineage:
    table = table_for(producer)
    return Lineage(
        sources=[SourceRef(producer or "UNKNOWN", file, row, record_id)],
        adapter=table.adapter_id,
        adapter_version=ADAPTER_VERSION,
    )


def to_number(value: Any, lineage: Lineage, field: str) -> float | None:
    """Parse a number, converting Arabic Indic digits (recorded as a repair)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        ascii_value = value.translate(ASCII_DIGITS).strip()
        try:
            number = float(ascii_value)
        except ValueError:
            return None
        if ascii_value != value:
            lineage.transformations.append(
                Transformation("ascii_digits", field, value, ascii_value, "Arabic Indic digits")
            )
        return number
    return None


def to_timestamp(value: Any, lineage: Lineage, field: str) -> datetime | None:
    """Parse ISO 8601 UTC, or repair an epoch number in seconds or milliseconds."""
    if isinstance(value, str) and is_utc_z(value):
        return parse_utc(value)
    number = None
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
    elif isinstance(value, str) and value.translate(ASCII_DIGITS).strip().isdigit():
        number = float(value.translate(ASCII_DIGITS).strip())
    if number is None:
        return None
    unit = "milliseconds" if number > 1e11 else "seconds"
    seconds = number / 1000.0 if unit == "milliseconds" else number
    moment = datetime.fromtimestamp(seconds, tz=UTC)
    lineage.transformations.append(
        Transformation("epoch_to_iso", field, value, format_utc(moment), f"epoch {unit}")
    )
    return moment


def normalise_segment_ref(value: Any, lineage: Lineage) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    match = _SEGMENT.match(value.strip())
    if not match:
        return value
    prefix, code, number = match.groups()
    prefix = SEGMENT_PREFIX_ALIASES.get(prefix.upper(), prefix.upper())
    fixed = f"{prefix}-{code.upper()}-{int(number):0{SEGMENT_NUMBER_WIDTH}d}"
    if fixed != value:
        lineage.transformations.append(
            Transformation("segment_ref_format", "segment_ref", value, fixed, "id scheme mapping")
        )
    return fixed


def drop_personal(record: dict[str, Any], flagged: set[str], lineage: Lineage) -> None:
    for key in list(record):
        if key in flagged or is_prohibited_field(key):
            del record[key]
            lineage.transformations.append(
                Transformation("drop_personal_field", key, WITHHELD, None, "quarantined field")
            )


def apply_aliases(record: dict[str, Any], lineage: Lineage) -> None:
    for alias, target in FIELD_ALIASES.items():
        if alias in record and target not in record:
            record[target] = record.pop(alias)
            lineage.transformations.append(
                Transformation("rename_field", target, alias, target, "schema drift alias")
            )


def in_bbox(lat: float, lon: float) -> bool:
    return (
        UAE_BBOX["lat_min"] <= lat <= UAE_BBOX["lat_max"]
        and UAE_BBOX["lon_min"] <= lon <= UAE_BBOX["lon_max"]
    )


def adapt_crash(
    raw: dict[str, Any],
    *,
    producer: str | None,
    file: str,
    row: int,
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], Lineage]:
    """Return the adapted crash fields and the lineage of how they were obtained."""
    rule_ids = {f["rule_id"] for f in findings}
    record = dict(raw)
    lineage = new_lineage(
        producer, file, row, raw.get("crash_id") if isinstance(raw.get("crash_id"), str) else None
    )
    lineage.findings = [
        {
            "rule_id": f["rule_id"],
            "field": f.get("field"),
            "detail": None if f["rule_id"].startswith("SK-P") else f.get("detail"),
        }
        for f in findings
    ]
    personal = {str(f.get("field")) for f in findings if f["rule_id"].startswith("SK-P")}
    drop_personal(record, personal, lineage)
    apply_aliases(record, lineage)

    occurred = to_timestamp(record.get("occurred_at"), lineage, "occurred_at")
    reported = to_timestamp(record.get("reported_at"), lineage, "reported_at")
    if "SK-X002" in rule_ids and occurred is not None:
        before = format_utc(occurred)
        occurred = occurred - LOCAL_OFFSET
        lineage.transformations.append(
            Transformation(
                "local_to_utc",
                "occurred_at",
                before,
                format_utc(occurred),
                "local time labelled as UTC; shifted by four hours",
            )
        )
        if reported is not None:
            reported = reported - LOCAL_OFFSET

    lat = to_number(record.get("lat"), lineage, "lat")
    lon = to_number(record.get("lon"), lineage, "lon")
    if lat is not None and lon is not None and not in_bbox(lat, lon) and in_bbox(lon, lat):
        lineage.transformations.append(
            Transformation("swap_lat_lon", "lat", lat, lon, "latitude and longitude swapped")
        )
        lat, lon = lon, lat
    if lat is not None and lon is not None and not in_bbox(lat, lon):
        lineage.notes.append("location outside the UAE bounding box; location discarded")
        lat = lon = None

    severity_raw = record.get("severity")
    severity = None
    if isinstance(severity_raw, str) and severity_raw in SEVERITY_CONTRACT:
        severity = SEVERITY_CONTRACT[severity_raw]
    elif str(severity_raw) in SEVERITY_LEGACY:
        severity = SEVERITY_LEGACY[str(severity_raw)]
        lossy = (
            " (lossy: code 2 mixes serious and minor injuries)"
            if str(severity_raw) in LOSSY_LEGACY
            else ""
        )
        lineage.transformations.append(
            Transformation(
                "severity_legacy_scale",
                "severity",
                severity_raw,
                severity,
                "legacy 1 to 3 scale" + lossy,
            )
        )
    vehicles_value = to_number(record.get("vehicles_involved"), lineage, "vehicles_involved")
    vehicles = (
        int(vehicles_value) if vehicles_value is not None and 1 <= vehicles_value <= 20 else None
    )

    duplicate = rule_ids & {"SK-S010", "SK-X003"}
    if duplicate:
        lineage.status = "rejected"
        lineage.notes.append("duplicate of an earlier record in the same feed")
    if occurred is None or lat is None or lon is None:
        lineage.status = "rejected"
        lineage.notes.append("no usable time or location")
    if lineage.status != "rejected" and lineage.transformations:
        lineage.status = "repaired"

    adapted = {
        "occurred": occurred,
        "reported": reported,
        "lat": lat,
        "lon": lon,
        "segment_ref": normalise_segment_ref(record.get("segment_ref"), lineage),
        "severity": severity,
        "vehicles": vehicles,
        "collision_type": record.get("collision_type"),
        "contributing_factors": record.get("contributing_factors"),
        "weather": record.get("weather"),
        "light_condition": record.get("light_condition"),
        "road_surface": record.get("road_surface"),
        "direction": record.get("direction"),
        "late": "SK-T002" in rule_ids,
    }
    if lineage.status != "rejected" and lineage.transformations and lineage.status != "repaired":
        lineage.status = "repaired"
    return adapted, lineage


def adapt_count(
    raw: dict[str, Any], *, rule_ids: set[str]
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Repair or reject one station interval.

    Returns the adapted interval (or None), the rejection reason, and the names of
    the repairs applied. Exposure lineage aggregates these per station, because a
    week of hourly rows would make per row lineage unreadable.
    """
    scratch = Lineage(sources=[], adapter="", adapter_version=ADAPTER_VERSION)
    record = dict(raw)
    apply_aliases(record, scratch)
    start = to_timestamp(record.get("interval_start"), scratch, "interval_start")
    minutes = to_number(record.get("interval_minutes"), scratch, "interval_minutes") or 60.0
    count = to_number(record.get("vehicle_count"), scratch, "vehicle_count")
    speed = to_number(record.get("mean_speed_kmh"), scratch, "mean_speed_kmh")
    repairs = [t.step for t in scratch.transformations]
    if start is None:
        return None, "no usable interval start", repairs
    if count is None or count < 0:
        return None, "missing or negative count", repairs
    if "SK-V010" in rule_ids:
        return None, "stuck sensor", repairs
    if "SK-V013" in rule_ids:
        start = start - LOCAL_OFFSET
        repairs.append("local_to_utc")
    if "SK-V011" in rule_ids:
        step = int(minutes * 60)
        start = datetime.fromtimestamp(int(start.timestamp()) // step * step, tz=UTC)
        repairs.append("floor_to_interval")
    if speed is not None and "SK-V008" in rule_ids:
        speed = speed * 3.6
        repairs.append("speed_ms_to_kmh")
    if speed is not None and ("SK-V002" in rule_ids or speed > 250):
        speed = None
        repairs.append("drop_impossible_speed")
    return {"start": start, "minutes": minutes, "count": count, "speed": speed}, None, repairs
