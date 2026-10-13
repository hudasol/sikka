from __future__ import annotations

import io
import json

import duckdb
import pytest

from sikka.contract.feedfile import render_csv, render_geojson, render_ndjson
from sikka.core import InputError
from sikka.ingest import (
    csv_row_to_record,
    detect_format,
    infer_feed_type,
    open_text,
    profile_feed,
    stage,
)

HEADER = {
    "producer_id": "PRODUCER_B",
    "feed_type": "crash_records",
    "contract_version": "1.0.0",
    "generated_at": "2026-01-20T06:00:00Z",
    "licence": "Apache-2.0",
    "synthetic": True,
    "record_count": 2,
    "period_start": "2020-12-31T20:00:00Z",
    "period_end": "2025-12-31T20:00:00Z",
}
RECORD = {
    "crash_id": "PB-0000001",
    "lat": 24.5,
    "lon": 54.4,
    "vehicles_involved": 2,
    "contributing_factors": ["fatigue", "speeding"],
    "severity": "fatal",
}


def _open(name: str, text: str):  # type: ignore[no-untyped-def]
    return open_text(name, io.StringIO(text))  # type: ignore[arg-type]


def test_detect_format() -> None:
    assert detect_format("a.NDJSON") == "ndjson"
    assert detect_format("a.jsonl") == "ndjson"
    assert detect_format("a.csv") == "csv"
    assert detect_format("a.geojson") == "geojson"
    with pytest.raises(InputError, match="unsupported"):
        detect_format("a.xlsx")


def test_infer_feed_type() -> None:
    assert infer_feed_type({"crash_id"}) == "crash_records"
    assert infer_feed_type({"station_id"}) == "traffic_counts"
    assert infer_feed_type({"x"}) is None


def test_ndjson_round_trip_keeps_json_types() -> None:
    parsed = _open("f.ndjson", render_ndjson(HEADER, [RECORD, RECORD | {"lat": "24.5"}]))
    assert parsed.header == HEADER
    assert parsed.feed_type == "crash_records"
    rows = [json.loads(r) for r in parsed.rows]
    assert rows[0]["lat"] == 24.5
    assert rows[1]["lat"] == "24.5"


def test_ndjson_without_header_keeps_first_record() -> None:
    text = json.dumps(RECORD) + "\n" + json.dumps(RECORD) + "\n"
    parsed = _open("f.ndjson", text)
    assert parsed.header is None
    assert parsed.header_error == "missing provenance header"
    assert parsed.feed_type == "crash_records"
    assert len(list(parsed.rows)) == 2


def test_csv_types_only_clean_ascii_numbers() -> None:
    arabic_two = chr(0x0662)
    text = render_csv(HEADER, [RECORD, RECORD | {"vehicles_involved": arabic_two}])
    parsed = _open("f.csv", text)
    rows = [json.loads(r) for r in parsed.rows]
    assert rows[0]["vehicles_involved"] == 2
    assert rows[0]["contributing_factors"] == ["fatigue", "speeding"]
    assert rows[1]["vehicles_involved"] == arabic_two


def test_csv_without_header_and_nested_columns() -> None:
    types = {"class_counts.car": "integer", "vehicle_count": "integer", "flag": "boolean"}
    record = csv_row_to_record(
        {"class_counts.car": "4", "vehicle_count": "-3", "flag": "true", "empty": ""}, types
    )
    assert record == {"class_counts": {"car": 4}, "vehicle_count": -3, "flag": True}
    parsed = _open("f.csv", "crash_id,lat\nPB-0000001,24.5\n")
    assert parsed.header is None
    # The feed type is inferred from the columns, so lat is typed as a number.
    assert [json.loads(r) for r in parsed.rows] == [{"crash_id": "PB-0000001", "lat": 24.5}]


def test_geojson_points_and_lines() -> None:
    point = {"type": "Point", "coordinates": [54.4, 24.5]}
    text = render_geojson(HEADER, [{"crash_id": "PB-0000001", "geometry": point}])
    rows = [json.loads(r) for r in _open("f.geojson", text).rows]
    assert rows[0]["lat"] == 24.5
    with pytest.raises(InputError, match="FeatureCollection"):
        _open("f.geojson", "[]")
    with pytest.raises(InputError, match="not valid JSON"):
        _open("f.geojson", "{")


def test_stage_and_profile_handle_invalid_lines() -> None:
    con = duckdb.connect()
    text = render_ndjson(HEADER, [RECORD]) + "{not json\n"
    feed = stage(con, _open("f.ndjson", text), "t")
    assert feed.rows == 2
    assert feed.producer_id == "PRODUCER_B"
    profile = profile_feed(con, feed)
    assert profile["invalid_json_rows"] == 1
    lat = next(f for f in profile["fields"] if f["field"] == "lat")
    assert lat["min"] == 24.5
    severity = next(f for f in profile["fields"] if f["field"] == "severity")
    assert severity["top_values"] == [{"value": "fatal", "count": 1}]


def test_stage_unknown_feed_type() -> None:
    con = duckdb.connect()
    feed = stage(con, _open("f.ndjson", '{"x": 1}\n'), "t")
    assert feed.feed_type is None
    assert profile_feed(con, feed)["fields"] == []
