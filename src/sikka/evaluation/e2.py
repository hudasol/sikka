"""E2: entity resolution against the ground truth.

Pairs are evaluated at the cluster level: two producer records are predicted to
be the same crash when they end up in the same canonical crash. Truth pairs are
records of different producers that share a true crash id. Abstention is the
share of candidate pairs left unresolved.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
from typing import Any

from sikka.conformance import Source
from sikka.core import mean_interval
from sikka.harmonise import HarmonisedDataset, harmonise
from sikka.synth import FAULTS, World, WorldConfig, build_world, finalise_feed, inject
from sikka.synth.world import truth_documents

SCENARIOS = {"clean": 0.0, "faults_5pct": 0.05}


def render_world(world: World) -> tuple[list[Source], dict[str, Any]]:
    finals = {}
    sources = []
    for feed in world.feeds:
        text, records = finalise_feed(feed)
        finals[feed.name] = records
        sources.append(Source.from_bytes(feed.filename, text.encode("utf-8")))
    return sources, truth_documents(world, finals)


def scenario_world(seed: int, scenario: str) -> World:
    world = build_world(WorldConfig(seed=seed))
    rate = SCENARIOS[scenario]
    if rate > 0:
        world = inject(world, dict.fromkeys(sorted(FAULTS), rate), seed=seed * 7 + 1)
    return world


def score_resolution(ds: HarmonisedDataset, truth: dict[str, Any]) -> dict[str, float]:
    true_id = {f"{r['file']}#{r['row']}": r["true_id"] for r in truth["record_map"]}
    by_true: dict[str, list[str]] = {}
    for key, tid in true_id.items():
        by_true.setdefault(tid, []).append(key)
    truth_pairs = set()
    for keys in by_true.values():
        for a, b in combinations(sorted(keys), 2):
            if a.split("#")[0] != b.split("#")[0]:
                truth_pairs.add((a, b))
    predicted = set()
    for crash in ds.crashes:
        keys = sorted(f"{s.file}#{s.row}" for s in crash.lineage.sources)
        for a, b in combinations(keys, 2):
            if a.split("#")[0] != b.split("#")[0]:
                predicted.add((a, b))
    hits = len(truth_pairs & predicted)
    precision = hits / len(predicted) if predicted else math.nan
    recall = hits / len(truth_pairs) if truth_pairs else math.nan
    f1 = (
        2 * precision * recall / (precision + recall)
        if predicted and truth_pairs and precision + recall > 0
        else math.nan
    )
    decisions = ds.decisions
    unresolved = sum(1 for d in decisions if d.decision == "unresolved")
    true_unresolved = sum(
        1
        for d in decisions
        if d.decision == "unresolved" and tuple(sorted((d.a, d.b))) in truth_pairs
    )
    reported = len({tid for key, tid in true_id.items()})
    return {
        "truth_pairs": float(len(truth_pairs)),
        "predicted_pairs": float(len(predicted)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "candidate_pairs": float(len(decisions)),
        "abstention_rate": unresolved / len(decisions) if decisions else math.nan,
        "unresolved_true_share": true_unresolved / unresolved if unresolved else math.nan,
        "canonical_crashes": float(len(ds.crashes)),
        "true_crashes_reported": float(reported),
        "count_error": (len(ds.crashes) - reported) / reported if reported else math.nan,
    }


def run_seed(seed: int, scenarios: list[str]) -> dict[str, Any]:
    out = {}
    for scenario in scenarios:
        sources, truth = render_world(scenario_world(seed, scenario))
        out[scenario] = score_resolution(harmonise(sources), truth)
    return {"seed": seed, "runs": out}


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return {"estimate": None, "low": None, "high": None, "n": 0}
    iv = mean_interval(finite)
    return {"estimate": iv.estimate, "low": iv.low, "high": iv.high, "n": len(finite)}


def run_e2(
    seeds: list[int], scenarios: list[str] | None = None, workers: int = 1
) -> dict[str, Any]:
    scenarios = scenarios or list(SCENARIOS)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_seed = list(pool.map(run_seed, seeds, [scenarios] * len(seeds)))
    else:
        per_seed = [run_seed(s, scenarios) for s in seeds]
    metrics = [
        "precision",
        "recall",
        "f1",
        "abstention_rate",
        "unresolved_true_share",
        "count_error",
    ]
    summary = {
        scenario: {m: _summary([s["runs"][scenario][m] for s in per_seed]) for m in metrics}
        for scenario in scenarios
    }
    return {
        "experiment": "E2",
        "title": "Entity resolution of crashes across producers",
        "seeds": seeds,
        "scenarios": {k: SCENARIOS[k] for k in scenarios},
        "summary": summary,
        "per_seed": per_seed,
    }
