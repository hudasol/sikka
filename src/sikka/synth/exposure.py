"""Synthetic exposure: true daily traffic per segment and hourly station counts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from sikka.core import LOCAL_TZ, format_utc, rng
from sikka.synth.config import WorldConfig
from sikka.synth.network import SegmentTruth

MEDIAN_AADT = {"motorway": 55000.0, "trunk": 28000.0, "primary": 14000.0, "secondary": 6000.0}

# Day of week factors, Monday first. The local weekend is Saturday and Sunday.
DOW_FACTOR = np.array([1.04, 1.05, 1.05, 1.04, 0.98, 0.90, 0.94])
DOW_FACTOR = DOW_FACTOR / DOW_FACTOR.mean()

# Share of daily traffic by local hour: morning and evening peaks.
_HOURS = np.arange(24)
HOUR_SHARE = (
    0.25
    + 1.2 * np.exp(-0.5 * ((_HOURS - 7.5) / 1.3) ** 2)
    + 1.0 * np.exp(-0.5 * ((_HOURS - 17.5) / 1.8) ** 2)
    + 0.35 * np.exp(-0.5 * ((_HOURS - 13.0) / 3.0) ** 2)
    - 0.18 * np.exp(-0.5 * ((_HOURS - 3.0) / 1.5) ** 2)
)
HOUR_SHARE = HOUR_SHARE / HOUR_SHARE.sum()

CLASS_SHARE = {
    "motorway": (0.74, 0.10, 0.11, 0.04, 0.01),
    "trunk": (0.77, 0.10, 0.08, 0.04, 0.01),
    "primary": (0.80, 0.10, 0.05, 0.04, 0.01),
    "secondary": (0.82, 0.10, 0.03, 0.03, 0.02),
}
CLASS_NAMES = ("car", "light_goods", "heavy_goods", "bus", "motorcycle")
LANE_CAPACITY_VPH = 1900.0
EFFECTIVE_VEHICLE_LENGTH_M = 6.5


@dataclass(frozen=True)
class Station:
    station_id: str
    segment_id: str
    owner: str
    classifies: bool


def true_aadt(config: WorldConfig, segments: list[SegmentTruth]) -> dict[str, float]:
    """Annual average daily traffic per segment, with a random walk along each corridor."""
    gen = rng(config.seed, "exposure", "aadt")
    out: dict[str, float] = {}
    walk = 0.0
    previous = None
    for seg in segments:
        if seg.corridor.code != previous:
            walk = float(gen.normal(0, 0.25))
            previous = seg.corridor.code
        walk += float(gen.normal(0, 0.08))
        noise = float(gen.normal(0, 0.10))
        out[seg.segment_id] = MEDIAN_AADT[seg.road_class] * math.exp(walk + noise)
    return out


def choose_stations(config: WorldConfig, segments: list[SegmentTruth]) -> list[Station]:
    gen = rng(config.seed, "exposure", "stations")
    stations: list[Station] = []
    for seg in segments:
        if gen.random() >= config.station_share:
            continue
        owner = seg.corridor.owner
        if owner == "PRODUCER_A":
            sid = f"STN-{seg.corridor.code}-{seg.index + 1:03d}"
        else:
            sid = f"CS-{seg.corridor.code}-{seg.index + 1:04d}"
        stations.append(Station(sid, seg.segment_id, owner, owner == "PRODUCER_A"))
    return stations


def count_week_start_utc(config: WorldConfig) -> datetime:
    local = datetime.fromisoformat(config.count_week_start_local).replace(tzinfo=LOCAL_TZ)
    return local.astimezone(UTC)


def station_counts(
    config: WorldConfig,
    segments: list[SegmentTruth],
    stations: list[Station],
    aadt: dict[str, float],
) -> dict[str, list[dict[str, object]]]:
    """Hourly count records per station for the count week."""
    by_id = {s.segment_id: s for s in segments}
    start = count_week_start_utc(config)
    hours = config.count_days * 24
    out: dict[str, list[dict[str, object]]] = {}
    for station in stations:
        gen = rng(config.seed, "exposure", "counts", station.station_id)
        seg = by_id[station.segment_id]
        free_flow = seg.speed_limit_kmh * float(gen.uniform(0.86, 0.97))
        shares = CLASS_SHARE[seg.road_class]
        records: list[dict[str, object]] = []
        for h in range(hours):
            moment = start + timedelta(hours=h)
            local = moment.astimezone(LOCAL_TZ)
            expected = aadt[seg.segment_id] * DOW_FACTOR[local.weekday()] * HOUR_SHARE[local.hour]
            count = int(gen.poisson(expected))
            per_lane = count / max(1, seg.lane_count)
            ratio = min(1.2, per_lane / LANE_CAPACITY_VPH)
            speed = free_flow * (1 - 0.35 * ratio**3) + float(gen.normal(0, 2.0))
            speed = max(5.0, speed)
            occupancy = per_lane * EFFECTIVE_VEHICLE_LENGTH_M / (speed * 1000.0) * 100.0
            occupancy = min(100.0, max(0.0, occupancy + float(gen.normal(0, 0.2))))
            flag_draw = gen.random()
            record: dict[str, object] = {
                "station_id": station.station_id,
                "segment_ref": station.segment_id,
                "interval_start": format_utc(moment),
                "interval_minutes": 60,
                "vehicle_count": count,
                "mean_speed_kmh": round(speed, 1),
                "occupancy_pct": round(occupancy, 2),
                "quality_flag": "ok"
                if flag_draw < 0.97
                else ("estimated" if flag_draw < 0.99 else "suspect"),
            }
            if station.classifies:
                split = gen.multinomial(count, shares)
                record["class_counts"] = {
                    name: int(n) for name, n in zip(CLASS_NAMES, split, strict=True)
                }
            record["__meta__"] = {"order": (station.station_id, h)}
            records.append(record)
        out[station.station_id] = records
    return out
