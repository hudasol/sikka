"""Segment table for analytics, built from the harmonised dataset.

Everything downstream is a pure function of this table, so it can be built from
any source that provides the same columns.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from sikka.core import LOCAL_TZ, is_utc_z, parse_utc
from sikka.harmonise import HarmonisedDataset

WINDOW_FIRST_YEAR = 2021
WINDOW_LAST_YEAR = 2025


@dataclass(frozen=True)
class AnalyticsConfig:
    first_year: int = WINDOW_FIRST_YEAR
    last_year: int = WINDOW_LAST_YEAR
    min_window_years: float = 3.0
    coverage_floor: float = 0.75
    top_k: int = 12
    draws: int = 4000
    interval: float = 0.90
    capture_pair_partner: str = "PRODUCER_B"

    @property
    def years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))


def _months(cfg: AnalyticsConfig) -> list[tuple[int, int]]:
    return [(y, m) for y in cfg.years for m in range(1, 13)]


def segment_table(ds: HarmonisedDataset, cfg: AnalyticsConfig | None = None) -> pd.DataFrame:
    """One row per registry segment with counts, exposure, coverage and quality inputs."""
    cfg = cfg or AnalyticsConfig()
    months = _months(cfg)
    window_start = datetime(cfg.first_year, 1, 1, tzinfo=LOCAL_TZ)
    window_end = datetime(cfg.last_year + 1, 1, 1, tzinfo=LOCAL_TZ)

    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    producers_on: dict[str, set[str]] = defaultdict(set)
    crash_segment: dict[str, str | None] = {}
    for crash in ds.crashes:
        crash_segment[crash.canonical_id] = crash.segment_id
        year = int(crash.attributes.get("local_year", 0))
        if crash.segment_id and cfg.first_year <= year <= cfg.last_year:
            counts[crash.segment_id][year] += 1
            producers_on[crash.segment_id].update(crash.producers)

    # Unresolved pairs: counted once, on the segment of the first crash of the pair.
    unresolved: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, str]] = set()
    for crash in ds.crashes:
        for other in crash.unresolved_with:
            pair = (min(crash.canonical_id, other), max(crash.canonical_id, other))
            if pair in seen:
                continue
            seen.add(pair)
            segment = crash_segment.get(pair[0]) or crash_segment.get(pair[1])
            if segment:
                unresolved[segment] += 1

    # Monthly delivery: months in which each producer's feed holds at least one usable record.
    delivered: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for pc in ds.producer_crashes:
        if pc.usable and pc.occurred_ts is not None:
            local = datetime.fromtimestamp(pc.occurred_ts, tz=UTC).astimezone(LOCAL_TZ)
            delivered[pc.producer_id].add((local.year, local.month))

    corridor_producers: dict[str, set[str]] = defaultdict(set)
    for segment_id, producers in producers_on.items():
        corridor_producers[segment_id.split("-")[1] if "-" in segment_id else ""] |= producers

    rows = []
    for sid, seg in sorted(ds.segments.items()):
        corridor = sid.split("-")[1] if sid.count("-") >= 2 else ""
        expected = sorted(corridor_producers.get(corridor, set()))
        coverage = (
            sum(len(delivered[p] & set(months)) / len(months) for p in expected) / len(expected)
            if expected
            else 0.0
        )
        start = window_start
        if seg.valid_from and is_utc_z(seg.valid_from):
            start = max(start, parse_utc(seg.valid_from).astimezone(LOCAL_TZ))
        window_years = max(0.0, (window_end - start).days / 365.25)
        exposure = ds.exposure.get(sid)
        by_year = counts.get(sid, {})
        rows.append(
            {
                "segment_id": sid,
                "corridor": corridor,
                "road_name_en": seg.road_name_en,
                "road_name_ar": seg.road_name_ar,
                "road_class": seg.road_class or "unknown",
                "lane_count": seg.lane_count or 0,
                "length_km": (seg.length_m or 0.0) / 1000.0,
                "owner": seg.owner_producer_id or "UNKNOWN",
                "aadt": exposure.aadt if exposure and exposure.aadt else None,
                "exposure_coverage": exposure.coverage if exposure else 0.0,
                "window_years": window_years,
                "observed": int(sum(by_year.values())),
                **{f"y{y}": int(by_year.get(y, 0)) for y in cfg.years},
                "unresolved_pairs": int(unresolved.get(sid, 0)),
                "producers_expected": ",".join(expected),
                "coverage": coverage,
            }
        )
    return pd.DataFrame(rows)


def group_capture_counts(
    ds: HarmonisedDataset, cfg: AnalyticsConfig | None = None
) -> dict[str, dict[str, int]]:
    """Per corridor owner: crashes reported by the owner, by the partner, and by both."""
    cfg = cfg or AnalyticsConfig()
    owners = {sid: seg.owner_producer_id for sid, seg in ds.segments.items()}
    out: dict[str, dict[str, int]] = {}
    for crash in ds.crashes:
        year = int(crash.attributes.get("local_year", 0))
        if not crash.segment_id or not cfg.first_year <= year <= cfg.last_year:
            continue
        owner = owners.get(crash.segment_id)
        if not owner:
            continue
        g = out.setdefault(owner, {"owner": 0, "partner": 0, "both": 0, "total": 0})
        by_owner = owner in crash.producers
        by_partner = cfg.capture_pair_partner in crash.producers
        g["owner"] += int(by_owner)
        g["partner"] += int(by_partner)
        g["both"] += int(by_owner and by_partner)
        g["total"] += 1
    return out
