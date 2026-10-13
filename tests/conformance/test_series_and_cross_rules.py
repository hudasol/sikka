"""Rules that need a series or several feeds: unit tests and property based tests."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sikka.conformance import BASE_RECORDS, Source
from sikka.core import LOCAL_TZ, format_utc
from sikka.synth.exposure import DOW_FACTOR, HOUR_SHARE

from .helpers import CLEAN, feed_bytes, flagged_rows, run_rules

SLOW = settings(max_examples=6, deadline=None, suppress_health_check=[HealthCheck.too_slow])
START = datetime(2025, 3, 2, 20, tzinfo=UTC)


def station_series(
    station: str = "STN-DUN-010",
    *,
    shift_hours: int = 0,
    speed_div: float = 1.0,
    occ_div: float = 1.0,
    aadt: float = 50000.0,
) -> list[dict[str, Any]]:
    rows = []
    for h in range(7 * 24):
        moment = START + timedelta(hours=h)
        local = moment.astimezone(LOCAL_TZ)
        count = int(aadt * DOW_FACTOR[local.weekday()] * HOUR_SHARE[local.hour]) + (h % 7)
        speed = 96.0 - (h % 5)
        occupancy = count / 8 * 6.5 / (speed * 1000) * 100
        rows.append(
            {
                "station_id": station,
                "segment_ref": "SEG-DUN-010",
                "interval_start": format_utc(moment + timedelta(hours=shift_hours)),
                "interval_minutes": 60,
                "vehicle_count": count,
                "mean_speed_kmh": round(speed / speed_div, 1),
                "occupancy_pct": round(occupancy / occ_div, 4),
                "quality_flag": "ok",
            }
        )
    return rows


def test_v008_flags_station_in_metres_per_second() -> None:
    rows = station_series("STN-A") + station_series("STN-B", speed_div=3.6)
    found = run_rules("traffic_counts", rows, {"SK-V008"})
    assert flagged_rows(found, "SK-V008") == set(range(169, 337))


def test_v009_flags_station_with_fractional_occupancy() -> None:
    rows = station_series("STN-A") + station_series("STN-B", occ_div=100.0)
    found = run_rules("traffic_counts", rows, {"SK-V009"})
    assert flagged_rows(found, "SK-V009") == set(range(169, 337))


@SLOW
@given(length=st.integers(min_value=2, max_value=20), start=st.integers(min_value=0, max_value=140))
def test_v010_flags_runs_of_six_or_more(length: int, start: int) -> None:
    rows = station_series()
    first = rows[start]
    for r in rows[start : start + length]:
        for key in ("vehicle_count", "mean_speed_kmh", "occupancy_pct"):
            r[key] = first[key]
    found = run_rules("traffic_counts", rows, {"SK-V010"})
    expected = set(range(start + 1, start + length + 1)) if length >= 6 else set()
    assert flagged_rows(found, "SK-V010") == expected


@SLOW
@given(shifted=st.integers(min_value=0, max_value=3), shift=st.sampled_from([4, 3, -2]))
def test_v013_flags_shifted_daily_profiles(shifted: int, shift: int) -> None:
    """Property within the rule's domain: shifted stations are a minority of the network."""
    rows: list[dict[str, Any]] = []
    for i in range(8):
        rows += station_series(f"STN-{i:03d}", shift_hours=shift if i < shifted else 0)
    found = run_rules("traffic_counts", rows, {"SK-V013"})
    flagged = set(found.loc[found["rule_id"] == "SK-V013", "series"])
    assert flagged == {f"STN-{i:03d}" for i in range(shifted)}


def test_v013_cannot_see_an_offset_shared_by_half_the_network() -> None:
    """Documented limitation: the median reference moves with a large shifted group."""
    rows: list[dict[str, Any]] = []
    for i in range(8):
        rows += station_series(f"STN-{i:03d}", shift_hours=4 if i < 4 else 0)
    found = run_rules("traffic_counts", rows, {"SK-V013"})
    assert found.empty


def test_r004_flags_rows_that_leave_the_usual_segment() -> None:
    rows = station_series()
    rows[10]["segment_ref"] = "SEG-DUN-030"
    found = run_rules("traffic_counts", rows, {"SK-R004"})
    assert flagged_rows(found, "SK-R004") == {11}


@SLOW
@given(drop=st.sets(st.integers(min_value=0, max_value=167), max_size=12))
def test_t001_counts_missing_intervals(drop: set[int]) -> None:
    rows = [r for i, r in enumerate(station_series()) if i not in drop]
    found = run_rules("traffic_counts", rows, {"SK-T001"})
    t001 = found[found["rule_id"] == "SK-T001"]
    if drop:
        assert t001["detail"].tolist() == [f"{len(drop)} of 168 intervals missing"]
    else:
        assert t001.empty


def crash(i: int, minutes: float = 0.0, north_m: float = 0.0, **extra: Any) -> dict[str, Any]:
    base = dict(BASE_RECORDS["crash_records"])
    occurred = datetime(2023, 5, 14, 17, 42, tzinfo=UTC) + timedelta(minutes=minutes)
    base.update(
        crash_id=f"PB-{i:07d}",
        occurred_at=format_utc(occurred),
        reported_at=format_utc(occurred + timedelta(hours=2)),
        lat=round(float(base["lat"]) + north_m / 110574.0, 6),  # type: ignore[arg-type]
    )
    base.update(extra)
    return base


@SLOW
@given(st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=8))
def test_s010_flags_every_repeat_after_the_first(ids: list[int]) -> None:
    records = [crash(i, minutes=97 * n) for n, i in enumerate(ids)]
    found = run_rules("crash_records", records, {"SK-S010"})
    seen: set[int] = set()
    expected = set()
    for row, i in enumerate(ids, 1):
        if i in seen:
            expected.add(row)
        seen.add(i)
    assert flagged_rows(found, "SK-S010") == expected


@SLOW
@given(minutes=st.floats(min_value=0, max_value=12), metres=st.floats(min_value=0, max_value=120))
def test_x003_flags_the_later_near_duplicate(minutes: float, metres: float) -> None:
    records = [crash(1), crash(2, minutes=minutes, north_m=metres)]
    found = run_rules("crash_records", records, {"SK-X003"})
    close = minutes <= 5 and metres <= 50 - 1
    if close:
        assert flagged_rows(found, "SK-X003") == {2}
    elif minutes > 5.01 or metres > 51:
        assert flagged_rows(found, "SK-X003") == set()


def _other_producer(records: list[dict[str, Any]]) -> Source:
    data = feed_bytes("crash_records", records, producer_id="PRODUCER_A")
    return Source.from_bytes("other.ndjson", data)


@SLOW
@given(minutes=st.floats(min_value=-40, max_value=40), metres=st.floats(min_value=0, max_value=400))
def test_x001_pairs_within_twenty_minutes_and_two_hundred_metres(
    minutes: float, metres: float
) -> None:
    from .helpers import registry_source

    other = crash(9, minutes=minutes, north_m=metres, producer_id="PRODUCER_A")
    found = run_rules(
        "crash_records",
        [crash(1)],
        {"SK-X001"},
        references=[registry_source(), _other_producer([other])],
    )
    inside = abs(minutes) <= 19.9 and metres <= 199
    outside = abs(minutes) > 20.1 or metres > 201
    if inside:
        assert flagged_rows(found, "SK-X001") == {1}
    elif outside:
        assert flagged_rows(found, "SK-X001") == set()


def test_x001_is_skipped_without_another_producer() -> None:
    found = run_rules("crash_records", [crash(1)], {"SK-X001"})
    assert found.empty


@SLOW
@given(offset=st.floats(min_value=-300, max_value=300), also_aligned=st.booleans())
def test_x002_flags_four_hour_offsets_only(offset: float, also_aligned: bool) -> None:
    from .helpers import registry_source

    others = [crash(9, minutes=-240 + offset, producer_id="PRODUCER_A")]
    if also_aligned:
        others.append(crash(8, minutes=0, producer_id="PRODUCER_A"))
    found = run_rules(
        "crash_records",
        [crash(1)],
        {"SK-X002"},
        references=[registry_source(), _other_producer(others)],
    )
    shifted = abs(offset) <= 19.9 and not also_aligned
    if shifted:
        assert flagged_rows(found, "SK-X002") == {1}
    elif abs(offset) > 20.1 or also_aligned:
        assert flagged_rows(found, "SK-X002") == set()


def _sample_registry() -> Source:
    return Source.from_path(CLEAN / "road_segments_producer_a.geojson")


def test_x005_flags_crashes_on_segments_with_tiny_exposure() -> None:
    segs = ["SEG-DUN-010", "SEG-DUN-011", "SEG-DUN-012", "SEG-DUN-013"]
    counts = []
    for seg in segs:
        for r in station_series(f"STN-{seg[-3:]}", aadt=60.0 if seg == "SEG-DUN-010" else 50000):
            counts.append(r | {"segment_ref": seg})
    counts_source = Source.from_bytes("counts.ndjson", feed_bytes("traffic_counts", counts))
    records = [crash(i, minutes=600 * i, segment_ref=segs[i % 4]) for i in range(8)]
    found = run_rules(
        "crash_records", records, {"SK-X005"}, references=[_sample_registry(), counts_source]
    )
    assert flagged_rows(found, "SK-X005") == {1, 5}


@SLOW
@given(missing=st.sets(st.integers(min_value=1, max_value=58), max_size=3))
def test_t003_flags_empty_months_when_they_are_unlikely(missing: set[int]) -> None:
    records = []
    n = 0
    for month in range(60):
        if month in missing:
            continue
        year, m = 2021 + month // 12, month % 12 + 1
        for day in (3, 9, 15, 21, 27, 28, 5, 11, 17, 23):
            n += 1
            when = datetime(year, m, day, 12, tzinfo=LOCAL_TZ).astimezone(UTC)
            records.append(
                crash(n)
                | {
                    "occurred_at": format_utc(when),
                    "reported_at": format_utc(when + timedelta(hours=3)),
                }
            )
    found = run_rules("crash_records", records, {"SK-T003"})
    t003 = found[found["rule_id"] == "SK-T003"]
    if missing:
        assert len(t003) == 1
        assert f"no records in {len(missing)} month(s)" in t003["detail"].iloc[0]
    else:
        assert t003.empty


def test_t003_is_silent_for_sparse_feeds() -> None:
    records = [crash(i, minutes=60 * 24 * 300 * i) for i in range(1, 6)]
    found = run_rules("crash_records", records, {"SK-T003"})
    assert found.empty
    assert math.exp(-1) > 0.001
