"""E3: blackspot ranking against the planted blackspots and the true ranks."""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from sikka.analytics import AnalyticsConfig, RankingBundle, rank_dataset
from sikka.core import mean_interval
from sikka.evaluation.e2 import render_world
from sikka.harmonise import harmonise
from sikka.synth import WorldConfig, build_world

METHODS = ("raw_count", "rate", "eb", "eb_qp")


def true_psi(truth: dict[str, Any]) -> pd.Series:
    """True potential for safety improvement per year: true long run rate minus SPF mean."""
    rows = truth["truth"]["segments"]
    return pd.Series(
        {r["segment_id"]: r["true_rate_per_year"] - r["spf_mean_per_year"] for r in rows}
    )


def method_tops(bundle: RankingBundle, k: int) -> dict[str, list[str]]:
    t = bundle.eb.table
    return {
        "raw_count": list(t.sort_values("raw_rank")["segment_id"].head(k)),
        "rate": list(t[t["rate_rank"].notna()].sort_values("rate_rank")["segment_id"].head(k)),
        "eb": bundle.eb.top(k),
        "eb_qp": bundle.eb_qp.top(k),
    }


def coverage_and_width(ranking_table: pd.DataFrame, psi: pd.Series) -> tuple[float, float]:
    """Share of ranked segments whose rank interval holds the true rank, and mean width."""
    ranked = ranking_table[ranking_table["abstained"] == ""].copy()
    if ranked.empty:
        return math.nan, math.nan
    ranked["true_psi"] = ranked["segment_id"].map(psi)
    order = ranked.sort_values(["true_psi", "segment_id"], ascending=[False, True])
    ranked.loc[order.index, "true_rank"] = np.arange(1, len(order) + 1)
    inside = (ranked["rank_low"] <= ranked["true_rank"]) & (
        ranked["true_rank"] <= ranked["rank_high"]
    )
    width = (ranked["rank_high"] - ranked["rank_low"]).mean()
    return float(inside.mean()), float(width)


def score_ranking(bundle: RankingBundle, truth: dict[str, Any]) -> dict[str, float]:
    k = bundle.config.top_k
    planted = {r["segment_id"] for r in truth["truth"]["segments"] if r["blackspot"]}
    with_exposure = set(bundle.eb.table.loc[bundle.eb.table["aadt"].notna(), "segment_id"])
    rankable = planted & with_exposure
    out: dict[str, float] = {
        "planted": float(len(planted)),
        "planted_rankable": float(len(rankable)),
    }
    for method, top in method_tops(bundle, k).items():
        top_set = set(top)
        out[f"{method}_recall_all"] = len(top_set & planted) / len(planted)
        out[f"{method}_recall_rankable"] = (
            len(top_set & rankable) / len(rankable) if rankable else math.nan
        )
    psi = true_psi(truth)
    for method, ranking in (("eb", bundle.eb), ("eb_qp", bundle.eb_qp)):
        cov, width = coverage_and_width(ranking.table, psi)
        out[f"{method}_coverage"] = cov
        out[f"{method}_width"] = width
    return out


def run_seed(seed: int) -> dict[str, Any]:
    sources, truth = render_world(build_world(WorldConfig(seed=seed)))
    bundle = rank_dataset(harmonise(sources), AnalyticsConfig(), seed=seed)
    return {"seed": seed, "scores": score_ranking(bundle, truth)}


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return {"estimate": None, "low": None, "high": None, "n": 0}
    iv = mean_interval(finite)
    return {"estimate": iv.estimate, "low": iv.low, "high": iv.high, "n": len(finite)}


def run_e3(seeds: list[int], workers: int = 1) -> dict[str, Any]:
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_seed = list(pool.map(run_seed, seeds))
    else:
        per_seed = [run_seed(s) for s in seeds]
    keys = sorted(per_seed[0]["scores"])
    return {
        "experiment": "E3",
        "title": "Blackspot ranking against planted blackspots",
        "seeds": seeds,
        "top_k": AnalyticsConfig().top_k,
        "methods": list(METHODS),
        "summary": {key: _summary([s["scores"][key] for s in per_seed]) for key in keys},
        "per_seed": per_seed,
    }
