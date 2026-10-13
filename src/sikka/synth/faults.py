"""Fault catalogue and injection.

Each fault has an id, a description, the feeds it can affect, the unit at which
it is measured (record, series or file), the conformance rule ids expected to
catch it, and an injection rate. The rate is the probability that each eligible
unit receives the fault; at least one unit is always affected so that recall
is defined in every run. Every injection is logged in the record metadata and
written to the ground truth sidecar by ``write_world``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import numpy as np

from sikka.core import LOCAL_TZ, format_utc, parse_utc, rng
from sikka.synth.network import SegmentTruth, to_lonlat, to_xy
from sikka.synth.world import Feed, World

Unit = Literal["record", "series", "file"]
ARABIC_INDIC = str.maketrans("0123456789", "".join(chr(0x0660 + i) for i in range(10)))
SEVERITY_LEGACY = {"fatal": 1, "serious_injury": 2, "minor_injury": 2, "property_damage_only": 3}


@dataclass
class FaultContext:
    world: World
    gen: np.random.Generator
    segments: dict[str, SegmentTruth]


@dataclass(frozen=True)
class Fault:
    id: str
    title: str
    description: str
    feed_types: tuple[str, ...]
    unit: Unit
    expected_rules: tuple[str, ...]
    default_rate: float
    apply: Callable[[FaultContext, float], None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "feed_types": list(self.feed_types),
            "unit": self.unit,
            "expected_rules": list(self.expected_rules),
            "default_rate": self.default_rate,
        }


def _pick(gen: np.random.Generator, n: int, rate: float) -> list[int]:
    """Indices chosen with probability ``rate``; at least one when ``n > 0``."""
    if n == 0:
        return []
    chosen = np.flatnonzero(gen.random(n) < rate).tolist()
    if not chosen:
        chosen = [int(gen.integers(0, n))]
    return [int(i) for i in chosen]


def _mark(record: dict[str, Any], fault_id: str) -> None:
    meta = record.setdefault("__meta__", {})
    faults = meta.setdefault("faults", [])
    if fault_id not in faults:
        faults.append(fault_id)


def _feeds(ctx: FaultContext, feed_type: str) -> list[Feed]:
    return [f for f in ctx.world.feeds if f.feed_type == feed_type]


def _records(
    ctx: FaultContext, feed_type: str, rate: float, key: str | None = None
) -> list[tuple[Feed, dict[str, Any]]]:
    """Pick records of a feed type (optionally only those that carry ``key``)."""
    pool = [
        (feed, r)
        for feed in _feeds(ctx, feed_type)
        for r in feed.records
        if key is None or key in r
    ]
    return [pool[i] for i in _pick(ctx.gen, len(pool), rate)]


def _stations(ctx: FaultContext, rate: float) -> list[tuple[Feed, str, list[dict[str, Any]]]]:
    pool: list[tuple[Feed, str, list[dict[str, Any]]]] = []
    for feed in _feeds(ctx, "traffic_counts"):
        by_station: dict[str, list[dict[str, Any]]] = {}
        for r in feed.records:
            by_station.setdefault(str(r.get("station_id")), []).append(r)
        pool.extend((feed, sid, rows) for sid, rows in sorted(by_station.items()))
    return [pool[i] for i in _pick(ctx.gen, len(pool), rate)]


def _xy(record: dict[str, Any]) -> tuple[float, float] | None:
    """Local km position of a record, or None when earlier faults made it unreadable."""
    try:
        return to_xy(float(record["lon"]), float(record["lat"]))
    except (KeyError, TypeError, ValueError):
        return None


def _shift_ts(value: Any, delta: timedelta) -> Any:
    if isinstance(value, str):
        try:
            return format_utc(parse_utc(value) + delta)
        except ValueError:
            return value
    return value


# Fault implementations ------------------------------------------------------


def f01_swap(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        r["lat"], r["lon"] = r["lon"], r["lat"]
        _mark(r, "F01")


def f02_outside(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        mode = int(ctx.gen.integers(0, 3))
        if mode == 0:
            r["lat"], r["lon"] = 0.0, 0.0
        elif mode == 1:
            r["lon"] = -float(r["lon"])
        else:
            r["lat"] = round(float(r["lat"]) + float(ctx.gen.uniform(5, 15)), 6)
        _mark(r, "F02")


def f03_local_as_utc(ctx: FaultContext, rate: float) -> None:
    four = timedelta(hours=4)
    for _, r in _records(ctx, "crash_records", rate):
        r["occurred_at"] = _shift_ts(r["occurred_at"], four)
        r["reported_at"] = _shift_ts(r["reported_at"], four)
        _mark(r, "F03")
    for _, _, rows in _stations(ctx, rate):
        for r in rows:
            r["interval_start"] = _shift_ts(r["interval_start"], four)
            _mark(r, "F03")


def f04_epoch(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        if not isinstance(r.get("occurred_at"), str):
            continue
        seconds = int(parse_utc(str(r["occurred_at"])).timestamp())
        r["occurred_at"] = seconds * 1000 if ctx.gen.random() < 0.5 else seconds
        _mark(r, "F04")


def f05_severity_scale(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        r["severity"] = SEVERITY_LEGACY.get(str(r["severity"]), 2)
        _mark(r, "F05")


def f06_speed_ms(ctx: FaultContext, rate: float) -> None:
    for _, _, rows in _stations(ctx, rate):
        for r in rows:
            r["mean_speed_kmh"] = round(float(r["mean_speed_kmh"]) / 3.6, 1)
            _mark(r, "F06")


def f07_occupancy_fraction(ctx: FaultContext, rate: float) -> None:
    for _, _, rows in _stations(ctx, rate):
        for r in rows:
            r["occupancy_pct"] = round(float(r["occupancy_pct"]) / 100.0, 4)
            _mark(r, "F07")


def f08_negative(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "traffic_counts", rate):
        r["vehicle_count"] = -max(2, int(r["vehicle_count"]))
        _mark(r, "F08")


def f09_impossible_speed(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "traffic_counts", rate):
        r["mean_speed_kmh"] = round(float(ctx.gen.uniform(260, 420)), 1)
        _mark(r, "F09")


def f10_stuck(ctx: FaultContext, rate: float) -> None:
    for _, _, rows in _stations(ctx, rate):
        length = int(ctx.gen.integers(8, 25))
        start = int(ctx.gen.integers(0, max(1, len(rows) - length)))
        first = rows[start]
        for r in rows[start : start + length]:
            for key in ("vehicle_count", "mean_speed_kmh", "occupancy_pct"):
                r[key] = first[key]
            if "class_counts" in first:
                r["class_counts"] = dict(first["class_counts"])
            _mark(r, "F10")


def f11_gaps(ctx: FaultContext, rate: float) -> None:
    for feed, sid, rows in _stations(ctx, rate):
        drop: set[int] = set()
        for _ in range(int(ctx.gen.integers(1, 4))):
            length = int(ctx.gen.integers(3, 13))
            start = int(ctx.gen.integers(1, max(2, len(rows) - length - 1)))
            drop.update(range(start, start + length))
        gone = {id(rows[i]) for i in drop if i < len(rows)}
        feed.records = [r for r in feed.records if id(r) not in gone]
        feed.series_faults.append(("F11", sid))


def f12_clock_drift(ctx: FaultContext, rate: float) -> None:
    for _, _, rows in _stations(ctx, rate):
        total_s = float(ctx.gen.uniform(600, 2400))
        for i, r in enumerate(rows):
            offset = round(total_s * i / max(1, len(rows) - 1))
            if offset >= 1:
                r["interval_start"] = _shift_ts(r["interval_start"], timedelta(seconds=offset))
                _mark(r, "F12")


def f13_renamed(ctx: FaultContext, rate: float) -> None:
    for feed in _feeds(ctx, "crash_records"):
        ordered = sorted(feed.records, key=lambda r: tuple(r["__meta__"]["order"]))
        n = max(1, math.ceil(rate * len(ordered)))
        for r in ordered[-n:]:
            if "occurred_at" in r:
                r["occurred_time"] = r.pop("occurred_at")
                _mark(r, "F13")


def f14_extra_field(ctx: FaultContext, rate: float) -> None:
    for feed_type in ("crash_records", "traffic_counts", "road_segments"):
        for _, r in _records(ctx, feed_type, rate):
            r["source_system"] = "LEGACY-7"
            _mark(r, "F14")


def f15_personal(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        mode = int(ctx.gen.integers(0, 4))
        if mode == 0:
            r["plate_number"] = "SYN 00000"
        elif mode == 1:
            r["driver_name"] = "Synthetic Person"
        elif mode == 2:
            r["contact"] = "+97150" + f"{int(ctx.gen.integers(0, 10_000_000)):07d}"
        else:
            r["reference"] = f"784-1900-{int(ctx.gen.integers(0, 10_000_000)):07d}-0"
        _mark(r, "F15")


def _corrupt_segment_id(gen: np.random.Generator, ident: str) -> str:
    prefix, code, number = ident.split("-")
    mode = int(gen.integers(0, 3))
    if mode == 0:
        return f"{prefix}-{code}-{int(number)}"
    if mode == 1:
        return f"S-{code}-{number}"
    return ident.lower()


def f16_segment_format(ctx: FaultContext, rate: float) -> None:
    for feed_type in ("crash_records", "traffic_counts"):
        for _, r in _records(ctx, feed_type, rate, key="segment_ref"):
            r["segment_ref"] = _corrupt_segment_id(ctx.gen, str(r["segment_ref"]))
            _mark(r, "F16")


def f17_mixed_names(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "road_segments", rate):
        if ctx.gen.random() < 0.5:
            r["road_name_en"] = r["road_name_ar"]
        else:
            r["road_name_ar"] = r["road_name_en"]
        _mark(r, "F17")


def f18_arabic_digits(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        key = "vehicles_involved" if ctx.gen.random() < 0.5 else "lat"
        r[key] = str(r[key]).translate(ARABIC_INDIC)
        _mark(r, "F18")
    for _, r in _records(ctx, "traffic_counts", rate):
        r["vehicle_count"] = str(r["vehicle_count"]).translate(ARABIC_INDIC)
        _mark(r, "F18")


def _bump_order(record: dict[str, Any], extra: str) -> None:
    order = list(record["__meta__"]["order"])
    order.append(extra)
    record["__meta__"]["order"] = tuple(order)


def f19_duplicate_within(ctx: FaultContext, rate: float) -> None:
    for feed, r in _records(ctx, "crash_records", rate):
        dup = {k: v for k, v in r.items() if k != "__meta__"}
        dup["__meta__"] = {k: v for k, v in r["__meta__"].items() if k != "faults"}
        _bump_order(dup, "~dup")
        dup["reported_at"] = _shift_ts(
            r.get("reported_at"), timedelta(minutes=int(ctx.gen.integers(1, 61)))
        )
        if ctx.gen.random() < 0.5:
            dup["crash_id"] = f"{r['crash_id']}-D"
        _mark(dup, "F19")
        feed.records.append(dup)


def f20_duplicate_across(ctx: FaultContext, rate: float) -> None:
    crash_feeds = _feeds(ctx, "crash_records")
    for source, r in _records(ctx, "crash_records", rate):
        targets = [f for f in crash_feeds if f.producer_id != source.producer_id]
        target = targets[int(ctx.gen.integers(0, len(targets)))]
        dup = {k: v for k, v in r.items() if k != "__meta__"}
        dup["__meta__"] = {k: v for k, v in r["__meta__"].items() if k != "faults"}
        _bump_order(dup, "~x")
        skew = timedelta(minutes=float(ctx.gen.uniform(-15, 15)))
        for key in ("occurred_at", "occurred_time"):
            if key in r:
                dup[key] = _shift_ts(r[key], skew)
        dup["reported_at"] = _shift_ts(r.get("reported_at"), timedelta(hours=1))
        angle = float(ctx.gen.uniform(0, 2 * math.pi))
        dist = 0.150 * math.sqrt(float(ctx.gen.random()))
        position = _xy(r)
        if position is not None:
            x, y = position[0] + dist * math.cos(angle), position[1] + dist * math.sin(angle)
            dup["lon"], dup["lat"] = to_lonlat(x, y)
        dup["producer_id"] = target.producer_id
        dup["crash_id"] = f"X-{target.producer_id[-1]}-{len(target.records) + 1:06d}"
        _mark(dup, "F20")
        target.records.append(dup)


def f21_late(ctx: FaultContext, rate: float) -> None:
    for feed in _feeds(ctx, "crash_records"):
        generated = parse_utc(str(feed.header["generated_at"]))
        eligible = [
            r
            for r in feed.records
            if isinstance(r.get("occurred_at"), str)
            and parse_utc(r["occurred_at"]) < generated - timedelta(days=61)
        ]
        for i in _pick(ctx.gen, len(eligible), rate):
            r = eligible[i]
            occurred = parse_utc(r["occurred_at"])
            room = (generated - occurred).days - 1
            delay = float(ctx.gen.uniform(60, min(700, room)))
            r["reported_at"] = format_utc(occurred + timedelta(days=delay))
            _mark(r, "F21")


def f22_off_network(ctx: FaultContext, rate: float) -> None:
    for _, r in _records(ctx, "crash_records", rate):
        position = _xy(r)
        if position is None:
            continue
        offset = float(ctx.gen.uniform(1.0, 8.0)) * (1 if ctx.gen.random() < 0.5 else -1)
        r["lon"], r["lat"] = to_lonlat(position[0], position[1] + offset)
        _mark(r, "F22")


def f23_partial_period(ctx: FaultContext, rate: float) -> None:
    feeds = [f for f in _feeds(ctx, "crash_records") if f.producer_id != "PRODUCER_D"]
    for i in _pick(ctx.gen, len(feeds), rate):
        feed = feeds[i]
        start = parse_utc(str(feed.header["period_start"])).astimezone(LOCAL_TZ)
        months = []
        year, month = start.year, start.month
        end = parse_utc(str(feed.header["period_end"])).astimezone(LOCAL_TZ)
        while (year, month) < (end.year, end.month):
            months.append((year, month))
            month += 1
            if month > 12:
                year, month = year + 1, 1
        k = int(ctx.gen.integers(1, 4))
        start_i = int(ctx.gen.integers(1, len(months) - k - 1))
        missing = set(months[start_i : start_i + k])

        def keep(r: dict[str, Any], missing: set[tuple[int, int]] = missing) -> bool:
            value = r.get("occurred_at")
            if not isinstance(value, str):
                return True
            local = parse_utc(value).astimezone(LOCAL_TZ)
            return (local.year, local.month) not in missing

        feed.records = [r for r in feed.records if keep(r)]
        feed.file_faults.append("F23")


def f24_record_count(ctx: FaultContext, rate: float) -> None:
    feeds = ctx.world.feeds
    for i in _pick(ctx.gen, len(feeds), rate):
        feed = feeds[i]
        delta = int(ctx.gen.integers(1, 51)) * (1 if ctx.gen.random() < 0.5 else -1)
        feed.header["record_count_override"] = max(0, len(feed.records) + delta)
        feed.file_faults.append("F24")


def f25_synthetic_false(ctx: FaultContext, rate: float) -> None:
    feeds = ctx.world.feeds
    for i in _pick(ctx.gen, len(feeds), rate):
        feeds[i].header["synthetic"] = False
        feeds[i].file_faults.append("F25")


CR, TC, RS = "crash_records", "traffic_counts", "road_segments"

CATALOGUE: tuple[Fault, ...] = (
    Fault(
        "F01",
        "Swapped latitude and longitude",
        "Latitude and longitude values are exchanged.",
        (CR,),
        "record",
        ("SK-V004", "SK-V003"),
        0.02,
        f01_swap,
    ),
    Fault(
        "F02",
        "Coordinates outside the UAE",
        "Coordinates set to zero, sign flipped or shifted far outside the bounding box.",
        (CR,),
        "record",
        ("SK-V003",),
        0.02,
        f02_outside,
    ),
    Fault(
        "F03",
        "Local time labelled as UTC",
        "Asia/Dubai local time written with a Z suffix, so the instant is four hours late.",
        (CR, TC),
        "record",
        ("SK-X002", "SK-V013"),
        0.02,
        f03_local_as_utc,
    ),
    Fault(
        "F04",
        "Epoch seconds or milliseconds",
        "A timestamp is written as an epoch number in seconds or milliseconds instead of ISO 8601.",
        (CR,),
        "record",
        ("SK-S011", "SK-S007"),
        0.02,
        f04_epoch,
    ),
    Fault(
        "F05",
        "Severity on a 1 to 3 scale",
        "Severity coded with a legacy numeric scale instead of the contract enumeration.",
        (CR,),
        "record",
        ("SK-S008",),
        0.02,
        f05_severity_scale,
    ),
    Fault(
        "F06",
        "Speed in metres per second",
        "A station reports mean speed in m/s.",
        (TC,),
        "record",
        ("SK-V008",),
        0.02,
        f06_speed_ms,
    ),
    Fault(
        "F07",
        "Occupancy as a fraction",
        "A station reports occupancy as 0 to 1 instead of percent.",
        (TC,),
        "record",
        ("SK-V009",),
        0.02,
        f07_occupancy_fraction,
    ),
    Fault(
        "F08",
        "Negative counts",
        "Vehicle counts below zero.",
        (TC,),
        "record",
        ("SK-V001",),
        0.02,
        f08_negative,
    ),
    Fault(
        "F09",
        "Impossible speeds",
        "Mean speeds above any plausible traffic speed.",
        (TC,),
        "record",
        ("SK-V002",),
        0.02,
        f09_impossible_speed,
    ),
    Fault(
        "F10",
        "Stuck sensor",
        "A station repeats identical values for 8 to 24 hours.",
        (TC,),
        "record",
        ("SK-V010",),
        0.02,
        f10_stuck,
    ),
    Fault(
        "F11",
        "Gaps in the time series",
        "Runs of 3 to 12 hourly intervals are missing.",
        (TC,),
        "series",
        ("SK-T001",),
        0.02,
        f11_gaps,
    ),
    Fault(
        "F12",
        "Clock drift",
        "A station clock drifts by 10 to 40 minutes over the week.",
        (TC,),
        "record",
        ("SK-V011",),
        0.02,
        f12_clock_drift,
    ),
    Fault(
        "F13",
        "Renamed field",
        "After a system change, occurred_at is written as occurred_time.",
        (CR,),
        "record",
        ("SK-S005", "SK-S006"),
        0.02,
        f13_renamed,
    ),
    Fault(
        "F14",
        "Unknown extra field",
        "Records carry a field the contract does not define.",
        (CR, TC, RS),
        "record",
        ("SK-S006",),
        0.02,
        f14_extra_field,
    ),
    Fault(
        "F15",
        "Personal data present",
        "A prohibited personal field, or a value that looks "
        "like a phone or identity number. All values are fake.",
        (CR,),
        "record",
        ("SK-P001", "SK-P002"),
        0.02,
        f15_personal,
    ),
    Fault(
        "F16",
        "Segment id format mismatch",
        "Segment references lose leading zeros, use a different prefix or lower case.",
        (CR, TC),
        "record",
        ("SK-R001", "SK-S009"),
        0.02,
        f16_segment_format,
    ),
    Fault(
        "F17",
        "Mixed Arabic and English names",
        "The English name field holds Arabic text or the Arabic field holds English text.",
        (RS,),
        "record",
        ("SK-V012",),
        0.02,
        f17_mixed_names,
    ),
    Fault(
        "F18",
        "Arabic Indic digits",
        "Numeric values written as strings with Arabic Indic digits.",
        (CR, TC),
        "record",
        ("SK-V005", "SK-S007"),
        0.02,
        f18_arabic_digits,
    ),
    Fault(
        "F19",
        "Duplicate within a feed",
        "The same crash appears twice in one feed, with the same or a new id.",
        (CR,),
        "record",
        ("SK-S010", "SK-X003"),
        0.02,
        f19_duplicate_within,
    ),
    Fault(
        "F20",
        "Duplicate across feeds",
        "The same crash appears in two producers' feeds "
        "with up to 15 minutes skew and 150 metres jitter. Natural overlaps between producers "
        "also count.",
        (CR,),
        "record",
        ("SK-X001",),
        0.02,
        f20_duplicate_across,
    ),
    Fault(
        "F21",
        "Late arriving records",
        "Reported 60 to 700 days after the crash.",
        (CR,),
        "record",
        ("SK-T002",),
        0.02,
        f21_late,
    ),
    Fault(
        "F22",
        "Crash outside any segment buffer",
        "Location moved 1 to 8 km off the network.",
        (CR,),
        "record",
        ("SK-R002",),
        0.02,
        f22_off_network,
    ),
    Fault(
        "F23",
        "Partial period",
        "One to three whole months of records are missing.",
        (CR,),
        "file",
        ("SK-T003",),
        0.02,
        f23_partial_period,
    ),
    Fault(
        "F24",
        "Declared record count mismatch",
        "The header record_count differs from the number of records.",
        (CR, TC, RS),
        "file",
        ("SK-S002",),
        0.02,
        f24_record_count,
    ),
    Fault(
        "F25",
        "Synthetic flag false",
        "The header says synthetic is false in a synthetic repository.",
        (CR, TC, RS),
        "file",
        ("SK-S003",),
        0.02,
        f25_synthetic_false,
    ),
)

FAULTS: dict[str, Fault] = {f.id: f for f in CATALOGUE}


def inject(world: World, rates: dict[str, float], seed: int) -> World:
    """Return a copy of ``world`` with the given faults injected at the given rates."""
    out = world.copy()
    segments = {s.segment_id: s for s in world.segments}
    for fault_id in sorted(rates):
        rate = rates[fault_id]
        if not 0 < rate <= 1:
            raise ValueError(f"rate for {fault_id} must be in (0, 1]")
        ctx = FaultContext(out, rng(seed, "faults", fault_id), segments)
        FAULTS[fault_id].apply(ctx, rate)
        out.injected[fault_id] = rate
    return out
