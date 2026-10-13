"""Value of information and survey mission planning (robotics link).

Plans are for simulation and review only. They are not flight authorisations.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from sikka.core import rng
from sikka.core.geo import project

DISCLAIMER = (
    "for simulation and review only; real flights need the operator's own safety case and the "
    "regulator's approval"
)


@dataclass(frozen=True)
class DroneProfile:
    """Default profile: 25 minutes endurance, 12 m/s, 20 percent reserve, 60 m altitude."""

    endurance_min: float = 25.0
    speed_mps: float = 12.0
    reserve_share: float = 0.20
    altitude_m: float = 60.0
    climb_mps: float = 3.0
    descent_mps: float = 2.0
    waypoint_spacing_m: float = 200.0

    @property
    def usable_s(self) -> float:
        return self.endurance_min * 60.0 * (1.0 - self.reserve_share)

    @property
    def vertical_s(self) -> float:
        return self.altitude_m / self.climb_mps + self.altitude_m / self.descent_mps

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"usable_s": self.usable_s}


@dataclass(frozen=True)
class TaskingConfig:
    max_missions: int = 4
    cost_per_km: float = 1.0
    min_value: float = 0.0
    profile: DroneProfile = field(default_factory=DroneProfile)


@dataclass
class Candidate:
    segment_id: str
    corridor: str
    index: int
    length_km: float
    p_top_k: float
    coordinates: list[list[float]]

    @property
    def voi(self) -> float:
        """Probability mass of uncertain top k membership: p (1 - p)."""
        return self.p_top_k * (1.0 - self.p_top_k)


def value_density(c: Candidate, cfg: TaskingConfig) -> float:
    """Value of information per unit survey cost (length times cost per km)."""
    cost = max(1e-6, c.length_km * cfg.cost_per_km)
    return c.voi / cost


@dataclass
class Mission:
    mission_id: str
    segments: list[str]
    waypoints: list[list[float]]  # [lon, lat, altitude above take off]
    path_km: float
    flight_s: float
    value: float
    feasible: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _segment_index(segment_id: str) -> int:
    tail = segment_id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def candidates_from_rows(
    rows: Sequence[dict[str, Any]], geometry: dict[str, list[list[float]]]
) -> list[Candidate]:
    out = []
    for r in rows:
        if r.get("abstained") or r.get("p_top_k") is None:
            continue
        sid = str(r["segment_id"])
        if sid not in geometry:
            continue
        out.append(
            Candidate(
                segment_id=sid,
                corridor=str(r["corridor"]),
                index=_segment_index(sid),
                length_km=float(r["length_km"]),
                p_top_k=float(r["p_top_k"]),
                coordinates=geometry[sid],
            )
        )
    return out


def _path_km(coords: list[list[float]]) -> float:
    arr = np.asarray(coords, dtype=np.float64)
    x, y = project(arr[:, 0], arr[:, 1])
    return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def _densify(coords: list[list[float]], spacing_m: float) -> list[list[float]]:
    out = [coords[0]]
    for a, b in itertools.pairwise(coords):
        piece = _path_km([a, b]) * 1000.0
        steps = max(1, math.ceil(piece / spacing_m))
        for s in range(1, steps + 1):
            t = s / steps
            out.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
    return out


def build_mission(mission_id: str, run: list[Candidate], cfg: TaskingConfig) -> Mission:
    """Fly along the run of adjacent segments, then straight back to the take off point."""
    profile = cfg.profile
    coords: list[list[float]] = []
    for c in run:
        part = c.coordinates if not coords else c.coordinates[1:]
        coords.extend(part)
    along = _path_km(coords)
    back = _path_km([coords[-1], coords[0]])
    path = along + back
    flight = path * 1000.0 / profile.speed_mps + profile.vertical_s
    waypoints = [
        [round(lon, 7), round(lat, 7), profile.altitude_m]
        for lon, lat in _densify(coords, profile.waypoint_spacing_m)
    ]
    feasible = flight <= profile.usable_s
    return Mission(
        mission_id=mission_id,
        segments=[c.segment_id for c in run],
        waypoints=waypoints,
        path_km=round(path, 3),
        flight_s=round(flight, 1),
        value=round(sum(c.voi for c in run), 6),
        feasible=feasible,
        reason="" if feasible else "flight time exceeds the usable endurance of the profile",
        metadata={
            "disclaimer": DISCLAIMER,
            "synthetic": True,
            "profile": profile.as_dict(),
            "home": coords[0],
        },
    )


def _grow(
    seed: Candidate,
    by_key: dict[tuple[str, int], Candidate],
    used: set[str],
    cfg: TaskingConfig,
    mission_id: str,
    by_value: bool,
) -> tuple[list[Candidate], Mission]:
    """Extend a one segment mission along its corridor while it fits the profile.

    Value of information missions extend towards the neighbour with the higher value
    density and only over segments with value; baseline missions simply follow the
    corridor forwards, then backwards, without looking at the value.
    """
    run = [seed]
    mission = build_mission(mission_id, run, cfg)
    while True:
        options = []
        for step in (1, -1):
            end = run[0] if step == -1 else run[-1]
            nxt = by_key.get((end.corridor, end.index + step))
            if nxt is None or nxt.segment_id in used:
                continue
            if by_value and nxt.voi <= cfg.min_value:
                continue
            options.append((value_density(nxt, cfg) if by_value else 0.0, step, nxt))
        options.sort(key=lambda o: (-o[0], -o[1]))
        extended = False
        for _, step, nxt in options:
            trial_run = [nxt, *run] if step == -1 else [*run, nxt]
            trial = build_mission(mission_id, trial_run, cfg)
            if trial.feasible:
                run, mission, extended = trial_run, trial, True
                break
        if not extended:
            return run, mission


def plan_missions(
    candidates: list[Candidate],
    cfg: TaskingConfig | None = None,
    order: list[str] | None = None,
) -> tuple[list[Mission], list[Mission]]:
    """Plan up to ``cfg.max_missions`` missions. Returns (planned, refused).

    Without ``order`` (value of information): each round grows a mission from every
    unused segment and keeps the feasible mission with the largest total value.
    With ``order`` (baselines): missions start at the next unused segment in that order.
    A segment that cannot be flown even alone is refused and listed with the reason.
    """
    cfg = cfg or TaskingConfig()
    by_key = {(c.corridor, c.index): c for c in candidates}
    by_id = {c.segment_id: c for c in candidates}
    used: set[str] = set()
    planned: list[Mission] = []
    refused: list[Mission] = []
    refused_ids: set[str] = set()

    def alone_feasible(c: Candidate) -> bool:
        single = build_mission(f"R{len(refused) + 1:02d}", [c], cfg)
        if not single.feasible and c.segment_id not in refused_ids:
            refused.append(single)
            refused_ids.add(c.segment_id)
        return single.feasible

    if order is None:
        while len(planned) < cfg.max_missions:
            mission_id = f"M{len(planned) + 1:02d}"
            best: tuple[float, str, list[Candidate], Mission] | None = None
            for c in sorted(candidates, key=lambda c: c.segment_id):
                if c.segment_id in used or c.voi <= cfg.min_value or not alone_feasible(c):
                    continue
                run, mission = _grow(c, by_key, used, cfg, mission_id, by_value=True)
                key = (mission.value, c.segment_id)
                if best is None or key[0] > best[0]:
                    best = (mission.value, c.segment_id, run, mission)
            if best is None:
                break
            used.update(c.segment_id for c in best[2])
            planned.append(best[3])
        return planned, refused

    for sid in order:
        if len(planned) >= cfg.max_missions:
            break
        seed = by_id.get(sid)
        if seed is None or sid in used or not alone_feasible(seed):
            continue
        run, mission = _grow(seed, by_key, used, cfg, f"M{len(planned) + 1:02d}", by_value=False)
        used.update(c.segment_id for c in run)
        planned.append(mission)
    return planned, refused


def random_order(candidates: list[Candidate], seed: int) -> list[str]:
    ids = sorted(c.segment_id for c in candidates)
    gen = rng(seed, "tasking", "random")
    return [ids[i] for i in gen.permutation(len(ids))]


def greedy_count_order(candidates: list[Candidate], observed: dict[str, int]) -> list[str]:
    return [
        c.segment_id
        for c in sorted(candidates, key=lambda c: (-observed.get(c.segment_id, 0), c.segment_id))
    ]
