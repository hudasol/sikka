"""Ranking by potential for safety improvement, with rank intervals and abstention."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from sikka.analytics.eb import empirical_bayes, posterior_draws
from sikka.analytics.inputs import AnalyticsConfig
from sikka.analytics.quality import Chapman
from sikka.analytics.spf import SpfFit, design_matrix, fit_spf
from sikka.core import rng

REASONS = ("no_exposure", "short_window", "low_coverage")


def abstention_reasons(df: pd.DataFrame, cfg: AnalyticsConfig) -> pd.Series:
    """Semicolon separated reasons per segment; empty when the segment is ranked."""
    reasons = []
    for _, row in df.iterrows():
        r = []
        if row["aadt"] is None or pd.isna(row["aadt"]) or float(row["aadt"]) <= 0:
            r.append("no_exposure")
        if float(row["window_years"]) < cfg.min_window_years:
            r.append("short_window")
        if float(row["coverage"]) < cfg.coverage_floor:
            r.append("low_coverage")
        reasons.append(";".join(r))
    return pd.Series(reasons, index=df.index, dtype="object")


def ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """Rank 1 for the largest score, per row; ties broken by column order."""
    order = np.argsort(-scores, axis=-1, kind="stable")
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, scores.shape[-1] + 1), axis=-1)
    return ranks


@dataclass
class Ranking:
    method: str
    table: pd.DataFrame
    spf: SpfFit | None
    chapman: dict[str, Chapman] = field(default_factory=dict)
    config: AnalyticsConfig = field(default_factory=AnalyticsConfig)

    @property
    def ranked(self) -> pd.DataFrame:
        return self.table[self.table["abstained"] == ""].sort_values("rank")

    @property
    def abstained(self) -> pd.DataFrame:
        return self.table[self.table["abstained"] != ""]

    def top(self, k: int | None = None) -> list[str]:
        return list(self.ranked["segment_id"].head(k or self.config.top_k))


def rank_segments(
    table: pd.DataFrame,
    cfg: AnalyticsConfig | None = None,
    *,
    seed: int = 0,
    chapman: dict[str, Chapman] | None = None,
    quality: bool = False,
) -> Ranking:
    """Empirical Bayes ranking (EB, or EB+QP when ``quality`` is true)."""
    cfg = cfg or AnalyticsConfig()
    df = table.copy().reset_index(drop=True)
    df["abstained"] = abstention_reasons(df, cfg)
    ok = df["abstained"] == ""
    rankable = df[ok].reset_index(drop=True)
    for col in (
        "predicted_per_year",
        "predicted",
        "eb",
        "eb_weight",
        "psi_per_year",
        "rank",
        "rank_median",
        "rank_low",
        "rank_high",
        "p_top_k",
        "quality_factor",
    ):
        df[col] = np.nan
    if len(rankable) < 8:
        return Ranking("eb_qp" if quality else "eb", _baselines(df), None, chapman or {}, cfg)

    fit = fit_spf(rankable)
    years = rankable["window_years"].to_numpy(dtype=np.float64)
    observed = rankable["observed"].to_numpy(dtype=np.float64)
    p_year = fit.predict_per_year(rankable)
    predicted = p_year * years
    eb = empirical_bayes(predicted, observed, fit.k, years)

    gen = rng(seed, "analytics", "eb_qp" if quality else "eb")
    x, names = design_matrix(rankable)
    beta_draws = gen.multivariate_normal(fit.coef, fit.cov, size=cfg.draws, method="cholesky")
    aligned = np.zeros((cfg.draws, len(names)))
    for i, name in enumerate(names):
        if name in fit.names:
            aligned[:, i] = beta_draws[:, fit.names.index(name)]
    p_draws = np.exp(aligned @ x.T) * years
    o_draws = np.broadcast_to(observed, (cfg.draws, len(observed))).copy()
    factor = np.ones(len(rankable))
    if quality:
        unresolved = rankable["unresolved_pairs"].to_numpy(dtype=np.int64)
        o_draws -= gen.binomial(unresolved, 0.5, size=(cfg.draws, len(unresolved)))
        o_draws = np.clip(o_draws, 0, None)
        for group, est in sorted((chapman or {}).items()):
            mask = (rankable["owner"] == group).to_numpy()
            if mask.any():
                f = est.factor_draws(gen, cfg.draws)
                o_draws[:, mask] *= f[:, None]
                factor[mask] = float(np.mean(f))
    m_draws = posterior_draws(p_draws, o_draws, fit.k, gen, cfg.draws)
    psi_draws = (m_draws - p_draws) / years
    rank_draws = ranks_from_scores(psi_draws)
    tail = (1 - cfg.interval) / 2
    point_rank = ranks_from_scores(eb.psi_per_year[None, :])[0]

    idx = np.flatnonzero(ok.to_numpy())
    df.loc[idx, "predicted_per_year"] = p_year
    df.loc[idx, "predicted"] = predicted
    df.loc[idx, "eb"] = eb.expected
    df.loc[idx, "eb_weight"] = eb.weight
    df.loc[idx, "psi_per_year"] = eb.psi_per_year
    df.loc[idx, "rank"] = point_rank
    df.loc[idx, "rank_median"] = np.median(rank_draws, axis=0)
    df.loc[idx, "rank_low"] = np.quantile(rank_draws, tail, axis=0, method="lower")
    df.loc[idx, "rank_high"] = np.quantile(rank_draws, 1 - tail, axis=0, method="higher")
    df.loc[idx, "p_top_k"] = np.mean(rank_draws <= cfg.top_k, axis=0)
    df.loc[idx, "quality_factor"] = factor
    return Ranking("eb_qp" if quality else "eb", _baselines(df), fit, chapman or {}, cfg)


def _baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Raw count rank over every segment and crash rate rank over segments with exposure."""
    out = df.copy()
    order = out.sort_values(["observed", "segment_id"], ascending=[False, True]).index
    out.loc[order, "raw_rank"] = np.arange(1, len(order) + 1)
    has = out["aadt"].notna() & (out["window_years"] > 0) & (out["length_km"] > 0)
    vkm = (
        out.loc[has, "aadt"].astype(float)
        * 365.0
        * out.loc[has, "window_years"]
        * out.loc[has, "length_km"]
        / 1e6
    )
    out["rate_per_mvkm"] = np.nan
    out.loc[has, "rate_per_mvkm"] = out.loc[has, "observed"] / vkm
    rate_order = (
        out[has].sort_values(["rate_per_mvkm", "segment_id"], ascending=[False, True]).index
    )
    out["rate_rank"] = np.nan
    out.loc[rate_order, "rate_rank"] = np.arange(1, len(rate_order) + 1)
    return out


def ranking_summary(r: Ranking) -> dict[str, Any]:
    reasons = {reason: int((r.table["abstained"].str.contains(reason)).sum()) for reason in REASONS}
    return {
        "method": r.method,
        "segments": len(r.table),
        "ranked": len(r.ranked),
        "abstained": len(r.abstained),
        "abstained_by_reason": reasons,
        "top_k": r.config.top_k,
        "draws": r.config.draws,
        "interval": r.config.interval,
    }
