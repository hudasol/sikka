"""Rank stability between a reference ranking and a ranking on degraded data."""

from __future__ import annotations

import math
from typing import Any

from scipy import stats

from sikka.analytics.ranking import Ranking


def rank_stability(reference: Ranking, other: Ranking, top_k: int | None = None) -> dict[str, Any]:
    """Kendall tau over segments ranked in both, and the overlap of the top k lists."""
    k = top_k or reference.config.top_k
    a = reference.ranked.set_index("segment_id")["psi_per_year"]
    b = other.ranked.set_index("segment_id")["psi_per_year"]
    common = sorted(set(a.index) & set(b.index))
    tau = math.nan
    if len(common) >= 3:
        tau = float(stats.kendalltau(a[common].to_numpy(), b[common].to_numpy()).statistic)
    top_a, top_b = set(reference.top(k)), set(other.top(k))
    overlap = len(top_a & top_b) / k if k else math.nan
    return {"kendall_tau": tau, "top_k_overlap": overlap, "common_segments": len(common), "k": k}


def baseline_stability(
    reference: Ranking, other: Ranking, top_k: int | None = None
) -> dict[str, Any]:
    """The same comparison for the raw count baseline."""
    k = top_k or reference.config.top_k
    a = reference.table.set_index("segment_id")["observed"]
    b = other.table.set_index("segment_id")["observed"]
    common = sorted(set(a.index) & set(b.index))
    tau = float(stats.kendalltau(a[common].to_numpy(), b[common].to_numpy()).statistic)
    top_a = set(reference.table.sort_values("raw_rank")["segment_id"].head(k))
    top_b = set(other.table.sort_values("raw_rank")["segment_id"].head(k))
    return {"kendall_tau": tau, "top_k_overlap": len(top_a & top_b) / k, "k": k}
