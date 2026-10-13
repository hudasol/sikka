"""Test helpers: build small feeds in memory and run selected rules."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from sikka.conformance import BASE_HEADER, BASE_RECORDS, Source, run_validation
from sikka.contract.feedfile import render_feed
from sikka.core import Paths

ROOT = Paths().root
CLEAN = ROOT / "data" / "samples" / "clean"


def _far_segment() -> dict[str, Any]:
    doc = json.loads((CLEAN / "road_segments_producer_a.geojson").read_text("utf-8"))
    for feature in doc["features"]:
        if feature["properties"]["segment_id"] == "SEG-DUN-030":
            return {**feature["properties"], "geometry": feature["geometry"]}
    raise AssertionError("SEG-DUN-030 missing from the sample registry")


TINY_REGISTRY = [dict(BASE_RECORDS["road_segments"]), _far_segment()]


def header(feed_type: str, **overrides: Any) -> dict[str, Any]:
    h = dict(BASE_HEADER) | {"feed_type": feed_type}
    if feed_type == "traffic_counts":
        h |= {
            "period_start": "2025-03-02T20:00:00Z",
            "period_end": "2025-03-09T20:00:00Z",
            "generated_at": "2025-03-10T22:00:00Z",
            "producer_id": "PRODUCER_A",
        }
    if feed_type == "road_segments":
        h |= {
            "period_start": "2020-01-01T00:00:00Z",
            "generated_at": "2026-01-05T06:00:00Z",
            "producer_id": "PRODUCER_A",
        }
    h.update(overrides)
    return h


def feed_bytes(
    feed_type: str, records: list[dict[str, Any]], fmt: str = "ndjson", **header_overrides: Any
) -> bytes:
    h = header(feed_type, **header_overrides)
    h.setdefault("record_count", len(records))
    if "record_count" not in header_overrides:
        h["record_count"] = len(records)
    return render_feed(fmt, h, records).encode("utf-8")  # type: ignore[arg-type]


def registry_source(records: list[dict[str, Any]] | None = None) -> Source:
    return Source.from_bytes(
        "registry.geojson", feed_bytes("road_segments", records or TINY_REGISTRY, "geojson")
    )


def run_rules(
    feed_type: str,
    records: list[dict[str, Any]],
    rule_ids: set[str],
    *,
    references: list[Source] | None = None,
    fmt: str | None = None,
    **header_overrides: Any,
) -> pd.DataFrame:
    """Validate one in memory feed and return the findings of the chosen rules."""
    fmt = fmt or ("geojson" if feed_type == "road_segments" else "ndjson")
    name = {"ndjson": "feed.ndjson", "csv": "feed.csv", "geojson": "feed.geojson"}[fmt]
    refs = [registry_source()] if references is None else references
    source = Source.from_bytes(name, feed_bytes(feed_type, records, fmt, **header_overrides))
    result = run_validation([source], refs, rule_ids=rule_ids)
    try:
        return result.all_findings()
    finally:
        result.close()


def flagged_rows(frame: pd.DataFrame, rule_id: str) -> set[int]:
    sub = frame[frame["rule_id"] == rule_id]
    return {int(r) for r in sub["_row"].dropna()}


def crash_like(i: int, **overrides: Any) -> dict[str, Any]:
    """The base crash record with a unique identifier."""
    return dict(BASE_RECORDS["crash_records"]) | {"crash_id": f"PB-{i:07d}"} | overrides
