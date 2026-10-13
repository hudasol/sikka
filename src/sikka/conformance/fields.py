"""Field specifications of the current contract, indexed for the rules."""

from __future__ import annotations

from functools import cache

from sikka.contract import CURRENT_VERSION, VERSIONS, FieldSpec, field_specs, version_schemas

ID_FIELDS = (
    "segment_id",
    "owner_producer_id",
    "crash_id",
    "producer_id",
    "segment_ref",
    "station_id",
)
RECORD_KEY = {
    "road_segments": "segment_id",
    "crash_records": "crash_id",
    "traffic_counts": "station_id",
}

# Base records that pass every record level rule against the sample registry.
# Rule examples override a few fields of these.
BASE_RECORDS: dict[str, dict[str, object]] = {
    "crash_records": {
        "crash_id": "PB-0000001",
        "producer_id": "PRODUCER_B",
        "occurred_at": "2023-05-14T17:42:00Z",
        "reported_at": "2023-05-14T19:05:00Z",
        "lat": 23.543057,
        "lon": 53.443151,
        "segment_ref": "SEG-DUN-010",
        "direction": "forward",
        "severity": "minor_injury",
        "vehicles_involved": 2,
        "collision_type": "rear_end",
        "contributing_factors": ["tailgating"],
        "weather": "clear",
        "light_condition": "dark_lit",
        "road_surface": "dry",
    },
    "traffic_counts": {
        "station_id": "STN-DUN-010",
        "segment_ref": "SEG-DUN-010",
        "interval_start": "2025-03-03T04:00:00Z",
        "interval_minutes": 60,
        "vehicle_count": 3200,
        "mean_speed_kmh": 92.5,
        "occupancy_pct": 2.75,
        "class_counts": {
            "car": 2400,
            "light_goods": 320,
            "heavy_goods": 350,
            "bus": 110,
            "motorcycle": 20,
        },
        "quality_flag": "ok",
    },
    "road_segments": {
        "segment_id": "SEG-DUN-010",
        "road_name_en": "Dune Corridor",
        "road_name_ar": "ممر الكثبان",
        "road_class": "motorway",
        "length_m": 1483.8,
        "lane_count": 8,
        "speed_limit_kmh": 100,
        "direction": "both",
        "owner_producer_id": "PRODUCER_A",
        "geometry": {
            "type": "LineString",
            "coordinates": [[53.433338, 23.54382], [53.443151, 23.543057], [53.447885, 23.542558]],
        },
        "valid_from": "2020-01-01T00:00:00Z",
    },
}

BASE_HEADER: dict[str, object] = {
    "producer_id": "PRODUCER_B",
    "feed_type": "crash_records",
    "contract_version": "1.0.0",
    "generated_at": "2026-01-20T06:00:00Z",
    "licence": "Apache-2.0",
    "synthetic": True,
    "record_count": 1,
    "period_start": "2020-12-31T20:00:00Z",
    "period_end": "2025-12-31T20:00:00Z",
}


@cache
def specs(feed_type: str) -> dict[str, FieldSpec]:
    schema = version_schemas(VERSIONS[CURRENT_VERSION])[feed_type]
    return {s.name: s for s in field_specs(schema, feed_type)}


def top_level(feed_type: str) -> dict[str, FieldSpec]:
    return {k: v for k, v in specs(feed_type).items() if "." not in k}


def allowed_keys(feed_type: str) -> list[str]:
    return list(top_level(feed_type))
