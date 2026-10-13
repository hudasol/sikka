"""How each invented producer observes the true crashes and writes its feed."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from sikka.core import LOCAL_TZ, format_utc, rng
from sikka.synth.config import ProducerProfile, WorldConfig
from sikka.synth.crashes import COLLISIONS, FACTORS, SEVERITIES, WEATHERS, TrueCrash
from sikka.synth.network import SegmentTruth, to_lonlat

SEVERE = {"fatal", "serious_injury"}


def _crash_id(profile: ProducerProfile, n: int, occurred: datetime) -> str:
    local = occurred.astimezone(LOCAL_TZ)
    return profile.id_style.format(year=local.year, n=n, date=local.strftime("%Y%m%d"))


def _perturb(gen: np.random.Generator, value: str, options: tuple[str, ...], p: float) -> str:
    if p > 0 and gen.random() < p:
        others = [o for o in options if o != value]
        return str(gen.choice(others))
    return value


def observe(
    config: WorldConfig,
    profile: ProducerProfile,
    crashes: list[TrueCrash],
    segments: dict[str, SegmentTruth],
    period: tuple[datetime, datetime],
) -> list[dict[str, object]]:
    """Return the producer's crash records, in arrival order, with private metadata."""
    gen = rng(config.seed, "producer", profile.producer_id)
    records: list[dict[str, object]] = []
    for crash in crashes:
        seg = segments[crash.segment_id]
        eligible = not (profile.own_corridors_only and seg.corridor.owner != profile.producer_id)
        eligible = eligible and not (profile.severe_only and crash.severity not in SEVERE)
        if not eligible or gen.random() >= profile.detection_rate:
            continue
        occurred = crash.occurred_utc + timedelta(
            minutes=float(gen.normal(0, profile.time_noise_min))
        )
        occurred = occurred.replace(second=0, microsecond=0)
        occurred = min(max(occurred, period[0]), period[1] - timedelta(minutes=1))
        delay_h = profile.delay_median_hours * math.exp(float(gen.normal(0, profile.delay_sigma)))
        reported = occurred + timedelta(hours=max(delay_h, 5 / 60))
        reported = reported.replace(microsecond=0)
        noise_km = profile.coord_noise_m / 1000.0
        x = crash.x_km + float(gen.normal(0, noise_km))
        y = crash.y_km + float(gen.normal(0, noise_km))
        lon, lat = to_lonlat(x, y)
        err = profile.attribute_error
        severity = crash.severity
        if err > 0 and gen.random() < err:
            i = SEVERITIES.index(severity)
            j = min(3, max(0, i + int(gen.choice([-1, 1]))))
            if not (profile.severe_only and SEVERITIES[j] not in SEVERE):
                severity = SEVERITIES[j]
        vehicles = crash.vehicles
        if err > 0 and gen.random() < err:
            vehicles = max(1, vehicles + int(gen.choice([-1, 1])))
        factors = list(crash.factors)
        if err > 0 and gen.random() < err and factors:
            factors[0] = _perturb(gen, factors[0], FACTORS, 1.0)
            factors = sorted(set(factors))
        record: dict[str, object] = {
            "crash_id": "",
            "producer_id": profile.producer_id,
            "occurred_at": format_utc(occurred),
            "reported_at": format_utc(reported),
            "lat": lat,
            "lon": lon,
        }
        if gen.random() < profile.segment_ref_share:
            record["segment_ref"] = crash.segment_id
        if gen.random() < profile.direction_share:
            record["direction"] = crash.direction
        record.update(
            {
                "severity": severity,
                "vehicles_involved": vehicles,
                "collision_type": _perturb(gen, crash.collision_type, COLLISIONS, err),
                "contributing_factors": factors,
                "weather": _perturb(gen, crash.weather, WEATHERS, err),
                "light_condition": crash.light,
                "road_surface": crash.surface,
            }
        )
        record["__meta__"] = {
            "true_id": crash.true_id,
            "order": (format_utc(reported), crash.true_id),
            "occurred_dt": occurred,
        }
        records.append(record)
    records.sort(key=lambda r: r["__meta__"]["order"])  # type: ignore[index]
    for n, record in enumerate(records, 1):
        meta = record["__meta__"]
        assert isinstance(meta, dict)
        record["crash_id"] = _crash_id(profile, n, meta["occurred_dt"])
        del meta["occurred_dt"]
    return records
