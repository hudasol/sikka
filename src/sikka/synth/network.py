"""Stylised synthetic corridor network on an invented local grid.

Corridors run roughly west to east, 30 km apart, with a gentle meander. The
grid is placed inside the UAE bounding box; it does not follow any real road.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from sikka.core import rng
from sikka.synth.config import CORRIDORS, Corridor, WorldConfig

ORIGIN_LAT = 24.2
ORIGIN_LON = 54.1
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320 * math.cos(math.radians(ORIGIN_LAT))

LANES = {"motorway": (6, 8), "trunk": (4, 6), "primary": (4, 4), "secondary": (2, 2)}
SPEEDS = {"motorway": (120, 140), "trunk": (100, 120), "primary": (80, 100), "secondary": (60, 80)}


def to_lonlat(x_km: float, y_km: float) -> tuple[float, float]:
    return (
        round(ORIGIN_LON + x_km / KM_PER_DEG_LON, 6),
        round(ORIGIN_LAT + y_km / KM_PER_DEG_LAT, 6),
    )


def to_xy(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - ORIGIN_LON) * KM_PER_DEG_LON, (lat - ORIGIN_LAT) * KM_PER_DEG_LAT)


@dataclass(frozen=True)
class SegmentTruth:
    segment_id: str
    corridor: Corridor
    index: int
    road_class: str
    lane_count: int
    speed_limit_kmh: int
    length_m: float
    xy: tuple[tuple[float, float], ...]

    @property
    def lonlat(self) -> list[list[float]]:
        return [list(to_lonlat(x, y)) for x, y in self.xy]

    def point_at(self, fraction: float) -> tuple[float, float]:
        """Point at a fraction of the length, in local km coordinates."""
        target = fraction * self.length_m / 1000.0
        walked = 0.0
        for (x0, y0), (x1, y1) in zip(self.xy, self.xy[1:], strict=False):
            piece = math.hypot(x1 - x0, y1 - y0)
            if walked + piece >= target or (x1, y1) == self.xy[-1]:
                t = 0.0 if piece == 0 else min(1.0, (target - walked) / piece)
                return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
            walked += piece
        return self.xy[-1]

    def heading_at(self, fraction: float) -> tuple[float, float]:
        """Unit direction vector at a fraction of the length."""
        a = self.point_at(max(0.0, fraction - 0.01))
        b = self.point_at(min(1.0, fraction + 0.01))
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy) or 1.0
        return (dx / norm, dy / norm)

    def registry_record(self, valid_from: str) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "road_name_en": self.corridor.name_en,
            "road_name_ar": self.corridor.name_ar,
            "road_class": self.road_class,
            "length_m": round(self.length_m, 1),
            "lane_count": self.lane_count,
            "speed_limit_kmh": self.speed_limit_kmh,
            "direction": "both",
            "owner_producer_id": self.corridor.owner,
            "geometry": {"type": "LineString", "coordinates": self.lonlat},
            "valid_from": valid_from,
        }


def _walk(
    x0: float, y0: float, amp: float, period: float, phase: float, length_km: float, step: float
) -> list[tuple[float, float]]:
    """Points every ``step`` km of arc length along y = y0 + amp sin(...)."""
    pts = [(x0, y0 + amp * math.sin(2 * math.pi * x0 / period + phase))]
    x = x0
    walked = 0.0
    fine = 0.01
    while walked < length_km - 1e-9:
        target = min(step, length_km - walked)
        travelled = 0.0
        while travelled < target - 1e-12:
            slope = amp * 2 * math.pi / period * math.cos(2 * math.pi * x / period + phase)
            dx = min(fine, target - travelled) / math.sqrt(1 + slope * slope)
            x += dx
            travelled += dx * math.sqrt(1 + slope * slope)
        walked += target
        pts.append((x, y0 + amp * math.sin(2 * math.pi * x / period + phase)))
    return pts


def build_network(config: WorldConfig) -> list[SegmentTruth]:
    gen = rng(config.seed, "network")
    segments: list[SegmentTruth] = []
    for ci, corridor in enumerate(CORRIDORS):
        lengths = np.clip(gen.lognormal(math.log(2.6), 0.55, config.segments_per_corridor), 0.5, 12)
        amp = float(gen.uniform(1.5, 4.0))
        period = float(gen.uniform(35, 70))
        phase = float(gen.uniform(0, 2 * math.pi))
        x = float(-95 + gen.uniform(-5, 5))
        y0 = -75.0 + 30.0 * ci
        lanes_lo, lanes_hi = LANES[corridor.road_class]
        speed_lo, speed_hi = SPEEDS[corridor.road_class]
        corridor_speed = int(gen.choice([speed_lo, speed_hi]))
        for si, length_km in enumerate(lengths):
            pts = _walk(x, y0, amp, period, phase, float(length_km), 0.5)
            x = pts[-1][0]
            lanes = int(gen.integers(lanes_lo // 2, lanes_hi // 2 + 1) * 2)
            speed = corridor_speed if gen.random() > 0.2 else max(speed_lo - 20, 60)
            segments.append(
                SegmentTruth(
                    segment_id=f"SEG-{corridor.code}-{si + 1:03d}",
                    corridor=corridor,
                    index=si,
                    road_class=corridor.road_class,
                    lane_count=lanes,
                    speed_limit_kmh=int(speed),
                    length_m=float(length_km) * 1000.0,
                    xy=tuple((round(px, 5), round(py, 5)) for px, py in pts),
                )
            )
    return segments
