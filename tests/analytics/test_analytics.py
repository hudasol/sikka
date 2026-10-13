from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from sikka.analytics import (
    AnalyticsConfig,
    Chapman,
    abstention_reasons,
    chapman_by_group,
    empirical_bayes,
    fit_spf,
    posterior_draws,
    rank_dataset,
    rank_segments,
    rank_stability,
    ranks_from_scores,
)
from sikka.analytics.sensitivity import baseline_stability
from sikka.core import rng
from sikka.evaluation.e2 import render_world
from sikka.harmonise import harmonise
from sikka.synth import WorldConfig, build_world


def test_eb_matches_a_worked_example() -> None:
    # Worked by hand: predicted 6 crashes over 3 years, observed 15, k = 2.
    # w = 1 / (1 + 6 / 2) = 0.25; EB = 0.25 * 6 + 0.75 * 15 = 12.75;
    # PSI per year = (12.75 - 6) / 3 = 2.25.
    out = empirical_bayes(np.array([6.0]), np.array([15.0]), k=2.0, years=np.array([3.0]))
    assert out.weight[0] == pytest.approx(0.25)
    assert out.expected[0] == pytest.approx(12.75)
    assert out.psi_per_year[0] == pytest.approx(2.25)


def test_second_worked_example_below_prediction() -> None:
    # P = 10 over 5 years, O = 4, k = 10: w = 0.5, EB = 7, PSI = -0.6 per year.
    out = empirical_bayes(np.array([10.0]), np.array([4.0]), k=10.0, years=np.array([5.0]))
    assert (out.weight[0], out.expected[0], out.psi_per_year[0]) == pytest.approx((0.5, 7.0, -0.6))


@given(
    p=st.floats(min_value=0.01, max_value=500),
    o=st.integers(min_value=0, max_value=2000),
    k=st.floats(min_value=0.05, max_value=50),
)
def test_eb_lies_between_prediction_and_observation(p: float, o: int, k: float) -> None:
    out = empirical_bayes(np.array([p]), np.array([float(o)]), k=k, years=np.array([5.0]))
    assert 0 < out.weight[0] <= 1
    lo, hi = min(p, o), max(p, o)
    assert lo - 1e-9 <= out.expected[0] <= hi + 1e-9
    assert np.sign(out.psi_per_year[0]) == np.sign(round(o - p, 9)) or abs(o - p) < 1e-9


def test_posterior_mean_is_the_eb_estimate() -> None:
    gen = rng(5, "test")
    draws = posterior_draws(np.array([6.0, 30.0]), np.array([15.0, 10.0]), 2.0, gen, 200_000)
    eb = empirical_bayes(np.array([6.0, 30.0]), np.array([15.0, 10.0]), 2.0, np.array([3.0, 3.0]))
    assert draws.mean(axis=0) == pytest.approx(eb.expected, rel=0.01)


def test_spf_recovers_known_coefficients() -> None:
    gen = rng(7, "spf")
    n = 3000
    aadt = np.exp(gen.normal(9.5, 0.8, n))
    length = np.exp(gen.normal(0.8, 0.5, n))
    classes = gen.choice(["motorway", "trunk", "primary", "secondary"], n)
    lanes = gen.choice([2, 4, 6], n)
    effect = pd.Series(classes).map({"motorway": 0, "trunk": 0.2, "primary": 0.3, "secondary": 0.5})
    mu = np.exp(-7.0 + 0.8 * np.log(aadt) + 1.0 * np.log(length) + effect - 0.05 * lanes) * 5
    alpha = 0.3
    lam = gen.gamma(1 / alpha, mu * alpha)
    df = pd.DataFrame(
        {
            "aadt": aadt,
            "length_km": length,
            "road_class": classes,
            "lane_count": lanes,
            "observed": gen.poisson(lam),
            "window_years": 5.0,
        }
    )
    fit = fit_spf(df)
    est = dict(zip(fit.names, fit.coef, strict=True))
    assert est["log_aadt"] == pytest.approx(0.8, abs=0.08)
    assert est["log_length_km"] == pytest.approx(1.0, abs=0.08)
    assert est["class_secondary"] == pytest.approx(0.5, abs=0.15)
    assert fit.alpha == pytest.approx(0.3, abs=0.08)
    assert fit.k == pytest.approx(1 / fit.alpha)
    assert 0 < fit.pseudo_r2 < 1
    assert fit.as_dict()["n_segments"] == n


def test_ranks_from_scores() -> None:
    ranks = ranks_from_scores(np.array([[0.5, 3.0, -1.0], [2.0, 2.0, 1.0]]))
    assert ranks.tolist() == [[2, 1, 3], [1, 2, 3]]


def test_abstention_reasons() -> None:
    df = pd.DataFrame(
        {
            "aadt": [10000.0, None, 5000.0, 5000.0, None],
            "window_years": [5.0, 5.0, 2.0, 5.0, 1.0],
            "coverage": [1.0, 1.0, 1.0, 0.5, 0.2],
        }
    )
    reasons = abstention_reasons(df, AnalyticsConfig()).tolist()
    assert reasons == [
        "",
        "no_exposure",
        "short_window",
        "low_coverage",
        "no_exposure;short_window;low_coverage",
    ]


def test_chapman_known_values() -> None:
    c = Chapman("G", n1=100, n2=80, m=40, union=140)
    assert c.estimate == pytest.approx(101 * 81 / 41 - 1)
    assert c.variance == pytest.approx(101 * 81 * 60 * 40 / (41**2 * 42))
    assert c.completeness == pytest.approx(140 / c.estimate)
    draws = c.factor_draws(rng(1, "c"), 20_000)
    assert draws.min() >= 1.0
    assert draws.mean() == pytest.approx(c.estimate / 140, rel=0.02)
    assert Chapman("E", 0, 0, 0, 0).factor_draws(rng(1, "c"), 3).tolist() == [1.0, 1.0, 1.0]
    groups = chapman_by_group({"A": {"owner": 10, "partner": 9, "both": 8, "total": 12}})
    assert groups["A"].union == 11
    assert groups["A"].as_dict()["estimated_total_low"] < groups["A"].estimate


SMALL = WorldConfig(seed=51, segments_per_corridor=12, target_total_crashes=1200.0)


@pytest.fixture(scope="module")
def bundle():  # type: ignore[no-untyped-def]
    sources, _ = render_world(build_world(SMALL))
    return rank_dataset(harmonise(sources), AnalyticsConfig(draws=1500), seed=3)


def test_ranking_outputs_are_consistent(bundle) -> None:  # type: ignore[no-untyped-def]
    for ranking in (bundle.eb, bundle.eb_qp):
        ranked = ranking.ranked
        assert len(ranked) + len(ranking.abstained) == len(ranking.table)
        assert (ranked["rank_low"] <= ranked["rank_median"]).all()
        assert (ranked["rank_median"] <= ranked["rank_high"]).all()
        assert ranked["p_top_k"].between(0, 1).all()
        # Every draw has exactly k segments in its top k, so the probabilities sum to k.
        assert ranked["p_top_k"].sum() == pytest.approx(ranking.config.top_k)
        assert sorted(ranked["rank"].astype(int)) == list(range(1, len(ranked) + 1))
        assert set(ranking.abstained["abstained"]) == {"no_exposure"}
    rows = bundle.segment_rows()
    assert len(rows) == len(bundle.table)
    abstained = [r for r in rows if r["abstained"]]
    assert all(r["rank"] is None for r in abstained)
    summary = bundle.summary()
    assert summary["published"]["method"] == "eb_qp"
    assert summary["spf"]["converged"]


def test_quality_propagation_widens_intervals(bundle) -> None:  # type: ignore[no-untyped-def]
    eb = bundle.eb.ranked
    qp = bundle.eb_qp.ranked
    assert (qp["rank_high"] - qp["rank_low"]).mean() >= (eb["rank_high"] - eb["rank_low"]).mean()
    assert (qp["quality_factor"] >= 1.0).all()


def test_ranking_is_deterministic(bundle) -> None:  # type: ignore[no-untyped-def]
    again = rank_segments(
        bundle.table, AnalyticsConfig(draws=1500), seed=3, chapman=bundle.chapman, quality=True
    )
    pd.testing.assert_frame_equal(again.table, bundle.eb_qp.table)


def test_stability_of_identical_rankings(bundle) -> None:  # type: ignore[no-untyped-def]
    same = rank_stability(bundle.eb, bundle.eb)
    assert same["kendall_tau"] == pytest.approx(1.0)
    assert same["top_k_overlap"] == 1.0
    assert baseline_stability(bundle.eb, bundle.eb)["top_k_overlap"] == 1.0


def test_too_few_segments_abstains_cleanly() -> None:
    df = pd.DataFrame(
        {
            "segment_id": ["S1"],
            "aadt": [None],
            "window_years": [5.0],
            "coverage": [1.0],
            "observed": [3],
            "length_km": [1.0],
            "road_class": ["trunk"],
            "lane_count": [4],
        }
    )
    ranking = rank_segments(df, AnalyticsConfig(draws=10))
    assert ranking.spf is None
    assert math.isnan(ranking.table["rank"].iloc[0])
    assert ranking.table["raw_rank"].iloc[0] == 1


@pytest.mark.perf
def test_ranking_performance_budget() -> None:
    sources, _ = render_world(build_world(WorldConfig(seed=61)))
    ds = harmonise(sources)
    started = time.perf_counter()
    rank_dataset(ds, AnalyticsConfig(draws=4000), seed=1)
    assert time.perf_counter() - started < 10.0
