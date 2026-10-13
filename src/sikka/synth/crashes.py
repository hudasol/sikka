"""True crash process: negative binomial counts with planted blackspots.

For segment ``i`` the safety performance function gives a yearly mean

    mu_i = exp(b0 + class_i + lane * lanes_i) * AADT_i ** a * (L_i / 1 km) ** b

A long run rate ``lambda_i`` is drawn from a gamma distribution with mean
``h_i * mu_i`` and shape ``k`` (so yearly counts are negative binomial), where
``h_i`` is 1 except on the planted blackspots. ``b0`` is calibrated so the
expected five year total matches ``target_total_crashes``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import numpy as np

from sikka.core import LOCAL_TZ, rng
from sikka.synth.config import WorldConfig
from sikka.synth.exposure import HOUR_SHARE
from sikka.synth.network import SegmentTruth

SEVERITIES = ("fatal", "serious_injury", "minor_injury", "property_damage_only")
SEVERITY_P = np.array([0.02, 0.10, 0.30, 0.58])
COLLISIONS = (
    "rear_end",
    "side_impact",
    "head_on",
    "rollover",
    "run_off_road",
    "pedestrian",
    "fixed_object",
    "other",
)
COLLISION_P = np.array([0.32, 0.18, 0.04, 0.08, 0.14, 0.03, 0.15, 0.06])
FACTORS = (
    "speeding",
    "tailgating",
    "sudden_swerving",
    "fatigue",
    "distraction",
    "mechanical_failure",
    "weather",
    "other",
)
FACTOR_P = np.array([0.25, 0.20, 0.15, 0.08, 0.15, 0.05, 0.05, 0.07])
WEATHERS = ("clear", "rain", "fog", "dust_sand", "strong_wind", "other")
WEATHER_P = np.array([0.85, 0.02, 0.04, 0.06, 0.02, 0.01])
NIGHT_RISK = np.where((np.arange(24) < 5) | (np.arange(24) >= 22), 1.8, 1.0)
CRASH_HOUR_P = HOUR_SHARE * NIGHT_RISK / float((HOUR_SHARE * NIGHT_RISK).sum())


@dataclass(frozen=True)
class SegmentHazard:
    segment_id: str
    aadt: float
    mu: float
    multiplier: float
    rate: float
    counts: tuple[int, ...]
    hotspot: float


@dataclass(frozen=True)
class TrueCrash:
    true_id: str
    segment_id: str
    occurred_utc: datetime
    x_km: float
    y_km: float
    fraction: float
    direction: str
    severity: str
    vehicles: int
    collision_type: str
    factors: tuple[str, ...]
    weather: str
    light: str
    surface: str


def _log_mu_without_b0(config: WorldConfig, seg: SegmentTruth, aadt: float) -> float:
    return (
        config.spf_class_effect[seg.road_class]
        + config.spf_lane_effect * seg.lane_count
        + config.spf_aadt_exponent * math.log(aadt)
        + config.spf_length_exponent * math.log(seg.length_m / 1000.0)
    )


def build_hazard(
    config: WorldConfig, segments: list[SegmentTruth], aadt: dict[str, float]
) -> tuple[float, dict[str, SegmentHazard]]:
    """Return the calibrated intercept ``b0`` and the hazard of every segment."""
    gen = rng(config.seed, "hazard")
    n = len(segments)
    blackspot_idx = set(gen.choice(n, size=config.n_blackspots, replace=False).tolist())
    lo, hi = config.blackspot_multiplier
    multipliers = [float(gen.uniform(lo, hi)) if i in blackspot_idx else 1.0 for i in range(n)]
    base = np.array([math.exp(_log_mu_without_b0(config, s, aadt[s.segment_id])) for s in segments])
    years = len(config.years)
    b0 = math.log(config.target_total_crashes / (years * float((base * multipliers).sum())))
    out: dict[str, SegmentHazard] = {}
    for i, seg in enumerate(segments):
        mu = math.exp(b0) * float(base[i])
        mean = mu * multipliers[i]
        rate = float(gen.gamma(config.dispersion_k, mean / config.dispersion_k))
        counts = tuple(int(c) for c in gen.poisson(rate, size=years))
        hotspot = float(gen.uniform(0.15, 0.85))
        out[seg.segment_id] = SegmentHazard(
            seg.segment_id, aadt[seg.segment_id], mu, multipliers[i], rate, counts, hotspot
        )
    return b0, out


def _light(hour: int, road_class: str, draw: float) -> str:
    if 6 <= hour < 17:
        return "daylight"
    if hour in (5, 17, 18):
        return "dawn_dusk"
    lit_share = {"motorway": 0.75, "trunk": 0.6, "primary": 0.5, "secondary": 0.3}[road_class]
    return "dark_lit" if draw < lit_share else "dark_unlit"


def build_crashes(
    config: WorldConfig, segments: list[SegmentTruth], hazard: dict[str, SegmentHazard]
) -> list[TrueCrash]:
    """Materialise every true crash with time, place and attributes."""
    gen = rng(config.seed, "crashes")
    crashes: list[TrueCrash] = []
    for seg in segments:
        hz = hazard[seg.segment_id]
        for year, n in zip(config.years, hz.counts, strict=True):
            start = datetime(year, 1, 1, tzinfo=LOCAL_TZ)
            days = (datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ) - start).days
            for _ in range(n):
                day = int(gen.integers(0, days))
                hour = int(gen.choice(24, p=CRASH_HOUR_P))
                minute = int(gen.integers(0, 60))
                local = start + timedelta(days=day, hours=hour, minutes=minute)
                at_hotspot = hz.multiplier > 1.0 and gen.random() < 0.7
                if at_hotspot:
                    fraction = float(np.clip(gen.normal(hz.hotspot, 0.04), 0.0, 1.0))
                else:
                    fraction = float(gen.random())
                x, y = seg.point_at(fraction)
                hx, hy = seg.heading_at(fraction)
                direction = "forward" if gen.random() < 0.5 else "reverse"
                side = 0.008 if direction == "forward" else -0.008
                x, y = x - hy * side, y + hx * side
                dark = hour < 6 or hour >= 19
                sev_p = SEVERITY_P.copy()
                if dark:
                    sev_p[0] *= 1.5
                    sev_p[1] *= 1.2
                sev_p = sev_p / sev_p.sum()
                severity = SEVERITIES[int(gen.choice(4, p=sev_p))]
                collision = COLLISIONS[int(gen.choice(len(COLLISIONS), p=COLLISION_P))]
                single = collision in {"rollover", "run_off_road", "fixed_object"}
                vehicles = 1 if single else min(20, 2 + int(gen.poisson(0.4)))
                n_factors = int(gen.choice([0, 1, 2], p=[0.1, 0.6, 0.3]))
                factors = tuple(
                    sorted(
                        FACTORS[i]
                        for i in gen.choice(len(FACTORS), size=n_factors, replace=False, p=FACTOR_P)
                    )
                )
                weather = WEATHERS[int(gen.choice(len(WEATHERS), p=WEATHER_P))]
                if weather == "rain":
                    surface = "wet"
                elif weather == "dust_sand" and gen.random() < 0.5:
                    surface = "sand_covered"
                else:
                    surface = "dry" if gen.random() < 0.97 else "damaged"
                crashes.append(
                    TrueCrash(
                        true_id="",
                        segment_id=seg.segment_id,
                        occurred_utc=local.astimezone(UTC),
                        x_km=x,
                        y_km=y,
                        fraction=fraction,
                        direction=direction,
                        severity=severity,
                        vehicles=vehicles,
                        collision_type=collision,
                        factors=factors,
                        weather=weather,
                        light=_light(hour, seg.road_class, float(gen.random())),
                        surface=surface,
                    )
                )
    crashes.sort(key=lambda c: (c.occurred_utc, c.segment_id, c.fraction))
    return [replace(c, true_id=f"T-{i + 1:06d}") for i, c in enumerate(crashes)]
