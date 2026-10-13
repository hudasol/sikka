from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from sikka.conformance import BASE_RECORDS
from sikka.evaluation.e2 import render_world, score_resolution
from sikka.harmonise import (
    MATCH_AT,
    NON_MATCH_BELOW,
    Lineage,
    ProducerCrash,
    SegmentIndex,
    adapt_count,
    adapt_crash,
    harmonise,
    normalise_segment_ref,
    resolve,
    score_pair,
    table_for,
)
from sikka.harmonise.adapters import to_number, to_timestamp
from sikka.harmonise.model import WITHHELD
from sikka.synth import WorldConfig, build_world, inject

ARABIC_DIGITS = "".join(chr(0x0660 + i) for i in range(10))


def lineage() -> Lineage:
    return Lineage(sources=[], adapter="t", adapter_version="1")


def crash(**extra: Any) -> dict[str, Any]:
    return dict(BASE_RECORDS["crash_records"]) | extra


def adapt(
    record: dict[str, Any], *rules: str, field: str | None = None
) -> tuple[dict[str, Any], Lineage]:
    findings = [{"rule_id": r, "field": field, "detail": "x"} for r in rules]
    return adapt_crash(record, producer="PRODUCER_B", file="f.ndjson", row=1, findings=findings)


def test_numbers_and_digits() -> None:
    lin = lineage()
    assert to_number(ARABIC_DIGITS[2] + ARABIC_DIGITS[4], lin, "lat") == 24.0
    assert lin.transformations[0].step == "ascii_digits"
    assert to_number(True, lin, "x") is None
    assert to_number("abc", lin, "x") is None
    assert to_number(float("nan"), lin, "x") is None


def test_timestamps() -> None:
    lin = lineage()
    assert to_timestamp("2023-05-14T17:42:00Z", lin, "t") == datetime(
        2023, 5, 14, 17, 42, tzinfo=UTC
    )
    seconds = int(datetime(2023, 5, 14, tzinfo=UTC).timestamp())
    assert to_timestamp(seconds, lin, "t") == datetime(2023, 5, 14, tzinfo=UTC)
    assert to_timestamp(seconds * 1000, lin, "t") == datetime(2023, 5, 14, tzinfo=UTC)
    assert [t.note for t in lin.transformations] == ["epoch seconds", "epoch milliseconds"]
    assert to_timestamp("yesterday", lin, "t") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SEG-DUN-7", "SEG-DUN-007"),
        ("S-DUN-007", "SEG-DUN-007"),
        ("seg-dun-007", "SEG-DUN-007"),
        ("SEG-DUN-007", "SEG-DUN-007"),
        ("ODD", "ODD"),
        (None, None),
    ],
)
def test_segment_ref_mapping(value: str | None, expected: str | None) -> None:
    assert normalise_segment_ref(value, lineage()) == expected


def test_clean_record_is_accepted_unchanged() -> None:
    out, lin = adapt(crash())
    assert lin.status == "accepted"
    assert out["severity"] == "minor_injury"
    assert lin.sources[0].record_id == "PB-0000001"
    assert lin.adapter == table_for("PRODUCER_B").adapter_id


def test_repairs_are_recorded_with_before_and_after() -> None:
    record = crash(lat=53.443151, lon=23.543057, severity=2, occurred_time="2023-05-14T21:42:00Z")
    del record["occurred_at"]
    out, lin = adapt(record, "SK-X002")
    steps = {t.step: t for t in lin.transformations}
    assert {"swap_lat_lon", "severity_legacy_scale", "rename_field", "local_to_utc"} <= set(steps)
    assert "lossy" in steps["severity_legacy_scale"].note
    assert out["occurred"] == datetime(2023, 5, 14, 17, 42, tzinfo=UTC)
    assert out["lat"] == pytest.approx(23.543057)
    assert lin.status == "repaired"


def test_personal_fields_are_dropped_without_keeping_values() -> None:
    _, lin = adapt(
        crash(plate_number="SYN 00000", contact="+971500000123"), "SK-P002", field="contact"
    )
    dropped = [t for t in lin.transformations if t.step == "drop_personal_field"]
    assert {t.field for t in dropped} == {"plate_number", "contact"}
    text = json.dumps(lin.as_dict())
    assert "SYN 00000" not in text
    assert "+971500000123" not in text
    assert WITHHELD in text
    assert all(f["detail"] is None for f in lin.findings if f["rule_id"].startswith("SK-P"))


def test_unusable_records_are_rejected() -> None:
    _, dup = adapt(crash(), "SK-S010")
    assert dup.status == "rejected"
    _, far = adapt(crash(lat=0.0, lon=0.0))
    assert far.status == "rejected"
    assert "outside the UAE" in far.notes[0]


def test_count_adapter() -> None:
    row = dict(BASE_RECORDS["traffic_counts"])
    ok, reason, repairs = adapt_count(row, rule_ids=set())
    assert ok is not None and reason is None and repairs == []
    neg, reason, _ = adapt_count(row | {"vehicle_count": -4}, rule_ids=set())
    assert neg is None and reason == "missing or negative count"
    stuck, reason, _ = adapt_count(row, rule_ids={"SK-V010"})
    assert stuck is None and reason == "stuck sensor"
    fixed, _, repairs = adapt_count(
        row | {"mean_speed_kmh": 30.0, "interval_start": "2025-03-03T08:07:00Z"},
        rule_ids={"SK-V008", "SK-V011", "SK-V013"},
    )
    assert fixed is not None
    assert fixed["speed"] == pytest.approx(108.0)
    assert fixed["start"] == datetime(2025, 3, 3, 4, 0, tzinfo=UTC)
    assert repairs == ["local_to_utc", "floor_to_interval", "speed_ms_to_kmh"]
    fast, _, repairs = adapt_count(row | {"mean_speed_kmh": 400.0}, rule_ids=set())
    assert fast is not None and fast["speed"] is None and "drop_impossible_speed" in repairs
    nostart, reason, _ = adapt_count(row | {"interval_start": "x"}, rule_ids=set())
    assert nostart is None and reason == "no usable interval start"


def test_segment_index() -> None:
    index = SegmentIndex.build(
        {
            "A": [[54.0, 24.0], [54.1, 24.0]],
            "B": [[54.0, 24.5], [54.1, 24.5]],
            "BAD": [[54.0, 24.0]],
        }
    )
    ids, dist = index.nearest(np.asarray([54.05, 54.05]), np.asarray([24.001, 24.49]))
    assert ids == ["A", "B"]
    assert dist[0] == pytest.approx(110.6, rel=0.02)
    assert index.distance_to(54.05, 24.001, "B") == pytest.approx(54_400, rel=0.02)
    assert index.distance_to(54.05, 24.001, "Z") is None
    empty_ids, empty_d = SegmentIndex.build({}).nearest(np.asarray([54.0]), np.asarray([24.0]))
    assert empty_ids == [None] and np.isinf(empty_d[0])


@given(
    dt=st.floats(min_value=0, max_value=29),
    extra_dt=st.floats(min_value=0.1, max_value=10),
    dist=st.floats(min_value=0, max_value=0.9),
    extra_dist=st.floats(min_value=0.001, max_value=0.1),
)
def test_score_falls_with_time_and_distance(
    dt: float, extra_dt: float, dist: float, extra_dist: float
) -> None:
    base = score_pair(dt, dist, "same", True)
    assert score_pair(dt + extra_dt, dist, "same", True) < base
    assert score_pair(dt, dist + extra_dist, "same", True) < base
    assert score_pair(dt, dist, "far", False) < base
    assert score_pair(dt, dist, "unknown", None) < base


def pc(
    key: str,
    producer: str,
    minutes: float,
    north_m: float,
    severity: str = "minor_injury",
    vehicles: int = 2,
) -> ProducerCrash:
    return ProducerCrash(
        key=key,
        producer_id=producer,
        occurred_ts=1_700_000_000 + minutes * 60,
        lat=24.0 + north_m / 110574.0,
        lon=54.0,
        segment_id="SEG-X-001",
        snap_distance_m=0,
        severity=severity,
        vehicles=vehicles,
        attributes={},
        lineage=Lineage(sources=[], adapter="t", adapter_version="1"),
    )


def test_resolution_decisions_and_one_to_one() -> None:
    crashes = [
        pc("b#1", "PRODUCER_B", 0, 0),
        pc("a#1", "PRODUCER_A", 2, 20),
        pc("a#2", "PRODUCER_A", 3, 30),
        pc("d#1", "PRODUCER_D", 25, 700, severity="fatal", vehicles=5),
        pc("c#1", "PRODUCER_C", 12, 180),
    ]
    decisions, clusters = resolve(crashes)
    by_pair = {tuple(sorted((d.a, d.b))): d.decision for d in decisions}
    assert by_pair[("a#1", "b#1")] == "match"
    assert by_pair[("a#2", "b#1")] == "unresolved"
    assert by_pair[("b#1", "d#1")] == "non_match"
    assert any(d.decision == "unresolved" for d in decisions if "c#1" in (d.a, d.b))
    members = [sorted(crashes[k].key for k in c) for c in clusters]
    assert ["a#1", "b#1"] in members
    assert all(len({crashes[k].producer_id for k in c}) == len(c) for c in clusters)
    assert MATCH_AT > NON_MATCH_BELOW


SMALL = WorldConfig(seed=41, segments_per_corridor=8, target_total_crashes=700.0)


@pytest.fixture(scope="module")
def small() -> tuple[Any, dict[str, Any]]:
    sources, truth = render_world(build_world(SMALL))
    return harmonise(sources), truth


def test_pipeline_against_truth(small: tuple[Any, dict[str, Any]]) -> None:
    ds, truth = small
    scores = score_resolution(ds, truth)
    assert scores["precision"] >= 0.98
    assert scores["recall"] >= 0.9
    assert abs(scores["count_error"]) < 0.1
    summary = ds.resolution_summary()
    assert (
        summary["match"] + summary["non_match"] + summary["unresolved"]
        == summary["candidate_pairs"]
    )


def test_lineage_index_covers_every_canonical_record(small: tuple[Any, dict[str, Any]]) -> None:
    ds, _ = small
    index = ds.lineage_index()
    assert {v["kind"] for v in index.values()} == {"crash", "exposure", "segment"}
    for crash_ in ds.crashes:
        entry = index[crash_.canonical_id]
        assert entry["lineage"]["sources"], crash_.canonical_id
    merged = [v for v in index.values() if v["lineage"]["merged_from"]]
    assert merged
    exposure = next(v for v in index.values() if v["kind"] == "exposure")
    assert exposure["record"]["aadt"] > 0
    assert 0 < exposure["record"]["coverage"] <= 1


def test_faulty_world_keeps_lineage_of_repairs() -> None:
    broken = inject(build_world(SMALL), {"F01": 0.1, "F04": 0.1, "F06": 0.2}, seed=3)
    sources, _ = render_world(broken)
    ds = harmonise(sources)
    steps = {t.step for c in ds.producer_crashes for t in c.lineage.transformations}
    assert {"swap_lat_lon", "epoch_to_iso"} <= steps
    exposure_steps = {t.step for e in ds.exposure.values() for t in e.lineage.transformations}
    assert "speed_ms_to_kmh" in exposure_steps
