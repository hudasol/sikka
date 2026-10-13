"""E1: fault detection. Per fault and injection rate, recall and precision of the rules.

Each run injects one fault into a clean synthetic world (isolation), validates the
feeds the fault can touch with only the fault's expected rules, and compares the
flagged units (records, station series or files) with the ground truth sidecar.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd

from sikka.conformance import Source, run_validation
from sikka.core import mean_interval
from sikka.synth import FAULTS, Fault, World, WorldConfig, build_world, finalise_feed, inject
from sikka.synth.world import truth_documents

Unit = tuple[str, ...]


def _render(world: World) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    finals = {}
    texts: dict[str, bytes] = {}
    for feed in world.feeds:
        text, records = finalise_feed(feed)
        finals[feed.name] = records
        texts[feed.filename] = text.encode("utf-8")
    faults = truth_documents(world, finals)["faults"]
    return texts, faults


def score_fault(fault: Fault, world: World) -> dict[str, float]:
    """Recall and precision of the fault's expected rules on one injected world."""
    texts, truth_rows = _render(world)
    types = {f.filename: f.feed_type for f in world.feeds}
    sources = [Source.from_bytes(n, b) for n, b in texts.items() if types[n] in fault.feed_types]
    refs = [
        Source.from_bytes(n, b)
        for n, b in texts.items()
        if types[n] == "road_segments" and types[n] not in fault.feed_types
    ]
    result = run_validation(sources, refs, rule_ids=set(fault.expected_rules))
    try:
        found = result.all_findings()
    finally:
        result.close()
    truth: set[Unit] = set()
    for r in truth_rows:
        if r["fault_id"] != fault.id:
            continue
        if fault.unit == "record":
            truth.add((r["file"], str(r["row"])))
        elif fault.unit == "series":
            truth.add((r["file"], str(r["series"])))
        else:
            truth.add((r["file"],))
    flagged: set[Unit] = set()
    for rule_id, file, row, series in zip(
        found["rule_id"], found["file"], found["_row"], found["series"], strict=True
    ):
        if rule_id not in fault.expected_rules:
            continue
        if fault.unit == "record" and not pd.isna(row):
            flagged.add((file, str(int(row))))
        elif fault.unit == "series" and isinstance(series, str):
            flagged.add((file, series))
        elif fault.unit == "file":
            flagged.add((file,))
    hits = len(truth & flagged)
    return {
        "truth": float(len(truth)),
        "flagged": float(len(flagged)),
        "hits": float(hits),
        "recall": hits / len(truth) if truth else math.nan,
        "precision": hits / len(flagged) if flagged else math.nan,
    }


def run_seed(seed: int, rates: list[float], fault_ids: list[str]) -> dict[str, Any]:
    clean = build_world(WorldConfig(seed=seed))
    out: dict[str, Any] = {}
    for i, fault_id in enumerate(fault_ids):
        for j, rate in enumerate(rates):
            broken = inject(clean, {fault_id: rate}, seed=seed * 1000 + i * 10 + j)
            out[f"{fault_id}|{rate}"] = score_fault(FAULTS[fault_id], broken)
    return {"seed": seed, "runs": out}


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return {"estimate": None, "low": None, "high": None, "n": 0, "undefined": len(values)}
    iv = mean_interval(finite)
    return {
        "estimate": iv.estimate,
        "low": max(0.0, iv.low),
        "high": min(1.0, iv.high),
        "n": len(finite),
        "undefined": len(values) - len(finite),
    }


def run_e1(
    seeds: list[int], rates: list[float], fault_ids: list[str] | None = None, workers: int = 1
) -> dict[str, Any]:
    fault_ids = fault_ids or sorted(FAULTS)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_seed = list(
                pool.map(run_seed, seeds, [rates] * len(seeds), [fault_ids] * len(seeds))
            )
    else:
        per_seed = [run_seed(s, rates, fault_ids) for s in seeds]
    faults: dict[str, Any] = {}
    for fault_id in fault_ids:
        fault = FAULTS[fault_id]
        by_rate: dict[str, Any] = {}
        for rate in rates:
            runs = [s["runs"][f"{fault_id}|{rate}"] for s in per_seed]
            by_rate[f"{rate:g}"] = {
                "recall": _summary([r["recall"] for r in runs]),
                "precision": _summary([r["precision"] for r in runs]),
                "mean_truth_units": sum(r["truth"] for r in runs) / len(runs),
                "mean_flagged_units": sum(r["flagged"] for r in runs) / len(runs),
            }
        faults[fault_id] = {
            "title": fault.title,
            "unit": fault.unit,
            "expected_rules": list(fault.expected_rules),
            "by_rate": by_rate,
        }
    return {
        "experiment": "E1",
        "title": "Fault detection by the conformance rules",
        "seeds": seeds,
        "rates": rates,
        "faults": faults,
        "per_seed": per_seed,
    }
