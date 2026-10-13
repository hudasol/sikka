"""E5: does value of information tasking reduce rank uncertainty more than the baselines?

A survey of a segment is simulated as two more years of crash data drawn from the
segment's true long run rate (hidden truth). Every strategy gets the same number
of missions under the default drone profile, and the same survey draws (common
random numbers), so differences come from which segments are chosen.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from sikka.analytics import (
    AnalyticsConfig,
    chapman_by_group,
    group_capture_counts,
    rank_segments,
    segment_table,
)
from sikka.core import mean_interval, rng
from sikka.evaluation.e2 import render_world
from sikka.harmonise import harmonise
from sikka.synth import WorldConfig, build_world
from sikka.tasking import TaskingConfig, compare_strategies

SURVEY_YEARS = 2.0
CFG = AnalyticsConfig(draws=1000)
STRATEGIES = ("value_of_information", "random", "greedy_crash_count")


def uncertainty_mass(table: pd.DataFrame) -> float:
    ranked = table[table["abstained"] == ""]
    p = ranked["p_top_k"].to_numpy(dtype=np.float64)
    return float(np.sum(p * (1.0 - p)))


def run_seed(seed: int) -> dict[str, Any]:
    sources, truth = render_world(build_world(WorldConfig(seed=seed)))
    ds = harmonise(sources)
    table = segment_table(ds, CFG)
    chapman = chapman_by_group(group_capture_counts(ds, CFG))
    base = rank_segments(table, CFG, seed=seed, chapman=chapman, quality=True)
    before = uncertainty_mass(base.table)
    rows: list[dict[str, Any]] = [
        {str(k): v for k, v in r.items()} for r in base.table.to_dict("records")
    ]
    geometry = {sid: seg.coordinates for sid, seg in ds.segments.items()}
    plans = compare_strategies(rows, geometry, TaskingConfig(), seed=seed)
    true_rate = {r["segment_id"]: r["true_rate_per_year"] for r in truth["truth"]["segments"]}
    gen = rng(seed, "survey")
    extra = {sid: int(gen.poisson(true_rate[sid] * SURVEY_YEARS)) for sid in sorted(true_rate)}
    out: dict[str, Any] = {"before": before}
    for name in STRATEGIES:
        surveyed = plans[name]["segments"]
        updated = table.copy()
        mask = updated["segment_id"].isin(surveyed)
        updated.loc[mask, "observed"] = (
            updated.loc[mask, "segment_id"].map(lambda s: extra[s]) + updated.loc[mask, "observed"]
        )
        updated.loc[mask, "window_years"] = updated.loc[mask, "window_years"] + SURVEY_YEARS
        after = uncertainty_mass(
            rank_segments(updated, CFG, seed=seed, chapman=chapman, quality=True).table
        )
        out[name] = {
            "after": after,
            "reduction": (before - after) / before if before > 0 else math.nan,
            "segments": len(surveyed),
            "missions": len(plans[name]["missions"]),
            "refused": len(plans[name]["refused"]),
            "flight_s": plans[name]["flight_s"],
        }
    return {"seed": seed, "runs": out}


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return {"estimate": None, "low": None, "high": None, "n": 0}
    iv = mean_interval(finite)
    return {"estimate": iv.estimate, "low": iv.low, "high": iv.high, "n": len(finite)}


def run_e5(seeds: list[int], workers: int = 1) -> dict[str, Any]:
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_seed = list(pool.map(run_seed, seeds))
    else:
        per_seed = [run_seed(s) for s in seeds]
    summary: dict[str, Any] = {}
    for name in STRATEGIES:
        for metric in ("reduction", "segments", "flight_s", "missions"):
            summary[f"{name}_{metric}"] = _summary(
                [float(s["runs"][name][metric]) for s in per_seed]
            )
    voi = [s["runs"]["value_of_information"]["reduction"] for s in per_seed]
    summary["seeds_voi_beats_random"] = sum(
        v > s["runs"]["random"]["reduction"] for v, s in zip(voi, per_seed, strict=True)
    )
    summary["seeds_voi_beats_greedy"] = sum(
        v > s["runs"]["greedy_crash_count"]["reduction"] for v, s in zip(voi, per_seed, strict=True)
    )
    return {
        "experiment": "E5",
        "title": "Value of information tasking against random and greedy tasking",
        "seeds": seeds,
        "strategies": list(STRATEGIES),
        "survey_years": SURVEY_YEARS,
        "draws": CFG.draws,
        "missions_budget": TaskingConfig().max_missions,
        "summary": summary,
        "per_seed": per_seed,
    }
