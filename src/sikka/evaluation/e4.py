"""E4: rank stability of the EB ranking (and the raw count baseline) under degraded data."""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from sikka.analytics import AnalyticsConfig, baseline_stability, rank_dataset, rank_stability
from sikka.core import mean_interval
from sikka.evaluation.e2 import render_world
from sikka.harmonise import harmonise
from sikka.synth import FAULTS, WorldConfig, build_world, inject

SCENARIOS = ("drop_A", "drop_B", "drop_C", "drop_D", "faults_5pct", "faults_20pct")
CFG = AnalyticsConfig(draws=1000)


def run_seed(seed: int) -> dict[str, Any]:
    clean = build_world(WorldConfig(seed=seed))
    sources, _ = render_world(clean)
    reference = rank_dataset(harmonise(sources), CFG, seed=seed)
    out: dict[str, Any] = {}
    for scenario in SCENARIOS:
        if scenario.startswith("drop_"):
            prefix = f"crash_records_producer_{scenario[-1].lower()}."
            degraded = [s for s in sources if not s.name.startswith(prefix)]
        else:
            rate = 0.05 if scenario == "faults_5pct" else 0.20
            broken = inject(
                clean, dict.fromkeys(sorted(FAULTS), rate), seed=seed * 13 + int(rate * 100)
            )
            degraded, _ = render_world(broken)
        bundle = rank_dataset(harmonise(degraded), CFG, seed=seed)
        out[scenario] = {
            "eb": rank_stability(reference.eb, bundle.eb),
            "raw_count": baseline_stability(reference.eb, bundle.eb),
        }
    return {"seed": seed, "runs": out}


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return {"estimate": None, "low": None, "high": None, "n": 0}
    iv = mean_interval(finite)
    return {"estimate": iv.estimate, "low": iv.low, "high": iv.high, "n": len(finite)}


def run_e4(seeds: list[int], workers: int = 1) -> dict[str, Any]:
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_seed = list(pool.map(run_seed, seeds))
    else:
        per_seed = [run_seed(s) for s in seeds]
    summary = {
        scenario: {
            method: {
                metric: _summary([s["runs"][scenario][method][metric] for s in per_seed])
                for metric in ("kendall_tau", "top_k_overlap")
            }
            for method in ("eb", "raw_count")
        }
        for scenario in SCENARIOS
    }
    return {
        "experiment": "E4",
        "title": "Rank stability under degraded data",
        "seeds": seeds,
        "scenarios": list(SCENARIOS),
        "draws": CFG.draws,
        "summary": summary,
        "per_seed": per_seed,
    }
