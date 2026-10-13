"""Entity resolution of crashes reported by more than one producer.

Blocking: candidate pairs come from different producers, within 30 minutes and
1 km of each other. Scoring: a log likelihood ratio (Fellegi and Sunter style)
of four comparisons, each with stated match (m) and non match (u) models:

* time difference: m = Normal(0, 6 min), u = Uniform over the 60 minute window;
* distance: m = Rayleigh with sigma 60 m, u = uniform over the 1 km disk;
* severity: same, adjacent class, or further apart;
* vehicles involved: equal or not.

Decision: match when the score is at least ``MATCH_AT``, non match below
``NON_MATCH_BELOW``, unresolved in between. Matches are one to one per producer
pair (greedy by score); a record with two strong candidates from the same
producer keeps the best and the other pair becomes unresolved. These numbers are
assumptions chosen before evaluation and are not fitted to the ground truth.
"""

from __future__ import annotations

import math
from collections import defaultdict

from sikka.core.geo import project
from sikka.harmonise.model import SEVERITY_RANK, PairDecision, ProducerCrash

WINDOW_MIN = 30.0
BLOCK_KM = 1.0
SIGMA_T_MIN = 6.0
SIGMA_D_KM = 0.06
MATCH_AT = 4.0
NON_MATCH_BELOW = 0.0
SEVERITY_M = {"same": 0.85, "adjacent": 0.13, "far": 0.02}
SEVERITY_U = {"same": 0.40, "adjacent": 0.35, "far": 0.25}
VEHICLES_M = {True: 0.85, False: 0.15}
VEHICLES_U = {True: 0.35, False: 0.65}


def severity_agreement(a: str | None, b: str | None) -> str:
    if a is None or b is None:
        return "unknown"
    gap = abs(SEVERITY_RANK[a] - SEVERITY_RANK[b])
    return "same" if gap == 0 else ("adjacent" if gap == 1 else "far")


def score_pair(dt_min: float, dist_km: float, severity: str, vehicles: bool | None) -> float:
    """Log likelihood ratio of match against non match."""
    window = 2 * WINDOW_MIN
    m_t = math.exp(-0.5 * (dt_min / SIGMA_T_MIN) ** 2) / (SIGMA_T_MIN * math.sqrt(2 * math.pi))
    llr = math.log(max(m_t, 1e-300) * window)
    # Rayleigh density over uniform in the disk: the distance factor cancels.
    llr += math.log(BLOCK_KM**2 / (2 * SIGMA_D_KM**2)) - dist_km**2 / (2 * SIGMA_D_KM**2)
    if severity != "unknown":
        llr += math.log(SEVERITY_M[severity] / SEVERITY_U[severity])
    if vehicles is not None:
        llr += math.log(VEHICLES_M[vehicles] / VEHICLES_U[vehicles])
    return llr


def candidate_pairs(crashes: list[ProducerCrash]) -> list[tuple[int, int, float, float]]:
    """Index pairs (i, j) with time difference in minutes and distance in km."""
    usable = [i for i, c in enumerate(crashes) if c.usable]
    xs: dict[int, tuple[float, float]] = {}
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for i in usable:
        c = crashes[i]
        x, y = project(c.lon, c.lat)  # type: ignore[arg-type]
        xs[i] = (float(x), float(y))
        key = (
            math.floor(float(x) / BLOCK_KM),
            math.floor(float(y) / BLOCK_KM),
            math.floor(c.occurred_ts / (WINDOW_MIN * 60)),  # type: ignore[operator]
        )
        buckets[key].append(i)
    pairs: list[tuple[int, int, float, float]] = []
    for (bx, by, bt), members in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dt in (-1, 0, 1):
                    other = buckets.get((bx + dx, by + dy, bt + dt))
                    if not other:
                        continue
                    for i in members:
                        for j in other:
                            if j <= i or crashes[i].producer_id == crashes[j].producer_id:
                                continue
                            gap = abs(crashes[i].occurred_ts - crashes[j].occurred_ts) / 60  # type: ignore[operator]
                            if gap > WINDOW_MIN:
                                continue
                            dist = math.dist(xs[i], xs[j])
                            if dist <= BLOCK_KM:
                                pairs.append((i, j, gap, dist))
    pairs.sort()
    return pairs


def resolve(crashes: list[ProducerCrash]) -> tuple[list[PairDecision], list[list[int]]]:
    """Decide every candidate pair and group matched records into clusters."""
    scored = []
    for i, j, gap, dist in candidate_pairs(crashes):
        a, b = crashes[i], crashes[j]
        sev = severity_agreement(a.severity, b.severity)
        veh = None if a.vehicles is None or b.vehicles is None else a.vehicles == b.vehicles
        scored.append((score_pair(gap, dist, sev, veh), i, j, gap, dist, sev, veh))
    scored.sort(key=lambda s: (-s[0], s[1], s[2]))
    taken: set[tuple[int, str]] = set()
    parent = list(range(len(crashes)))
    producers: dict[int, set[str]] = {i: {c.producer_id} for i, c in enumerate(crashes)}

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    decisions: list[PairDecision] = []
    for score, i, j, gap, dist, sev, veh in scored:
        a, b = crashes[i], crashes[j]
        if score >= MATCH_AT:
            ri, rj = find(i), find(j)
            conflict = (
                (i, b.producer_id) in taken
                or (j, a.producer_id) in taken
                or (ri != rj and producers[ri] & producers[rj])
            )
            if conflict:
                decision = "unresolved"
            else:
                decision = "match"
                taken.add((i, b.producer_id))
                taken.add((j, a.producer_id))
                if ri != rj:
                    parent[rj] = ri
                    producers[ri] |= producers.pop(rj)
        elif score < NON_MATCH_BELOW:
            decision = "non_match"
        else:
            decision = "unresolved"
        decisions.append(
            PairDecision(
                crashes[i].key,
                crashes[j].key,
                round(score, 4),
                decision,  # type: ignore[arg-type]
                round(gap, 3),
                round(dist * 1000, 1),
                sev,
                bool(veh),
            )
        )
    clusters: dict[int, list[int]] = defaultdict(list)
    for k, c in enumerate(crashes):
        if c.usable:
            clusters[find(k)].append(k)
    decisions.sort(key=lambda d: (d.a, d.b))
    return decisions, sorted(clusters.values())
