"""E1: fault detection. Per fault and injection rate, recall and precision of the rules.

Isolation runs inject one fault into a clean synthetic world, validate the feeds
the fault can touch with only the fault's expected rules, and compare the flagged
units (records, station series or files) with the ground truth sidecar.

The combined run injects every fault at 5 percent at once and runs every rule;
precision is then measured against any injected fault.

The baseline is a schema only check: every record and header is validated
against the contract models, without the conformance rules.
"""

from __future__ import annotations

import io
import json
import math
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd
from pydantic import ValidationError

from sikka.conformance import Source, run_validation
from sikka.contract import FEED_MODELS, ProvenanceHeader
from sikka.core import mean_interval
from sikka.ingest import open_text
from sikka.synth import FAULTS, Fault, World, WorldConfig, build_world, finalise_feed, inject
from sikka.synth.world import truth_documents

Unit = tuple[str, ...]
COMBINED_RATE = 0.05
BASELINE_RATE = 0.05


def _render(world: World) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    finals = {}
    texts: dict[str, bytes] = {}
    for feed in world.feeds:
        text, records = finalise_feed(feed)
        finals[feed.name] = records
        texts[feed.filename] = text.encode("utf-8")
    faults = truth_documents(world, finals)["faults"]
    return texts, faults


def truth_units(fault: Fault, truth_rows: list[dict[str, Any]]) -> set[Unit]:
    out: set[Unit] = set()
    for r in truth_rows:
        if r["fault_id"] != fault.id:
            continue
        if fault.unit == "record":
            out.add((r["file"], str(r["row"])))
        elif fault.unit == "series":
            out.add((r["file"], str(r["series"])))
        else:
            out.add((r["file"],))
    return out


def flagged_units(fault: Fault, found: pd.DataFrame) -> set[Unit]:
    out: set[Unit] = set()
    for rule_id, file, row, series in zip(
        found["rule_id"], found["file"], found["_row"], found["series"], strict=True
    ):
        if rule_id not in fault.expected_rules:
            continue
        if fault.unit == "record" and not pd.isna(row):
            out.add((file, str(int(row))))
        elif fault.unit == "series" and isinstance(series, str):
            out.add((file, series))
        elif fault.unit == "file":
            out.add((file,))
    return out


def _scores(truth: set[Unit], flagged: set[Unit]) -> dict[str, float]:
    hits = len(truth & flagged)
    return {
        "truth": float(len(truth)),
        "flagged": float(len(flagged)),
        "hits": float(hits),
        "recall": hits / len(truth) if truth else math.nan,
        "precision": hits / len(flagged) if flagged else math.nan,
    }


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
    return _scores(truth_units(fault, truth_rows), flagged_units(fault, found))


def schema_baseline(fault: Fault, world: World) -> dict[str, float]:
    """Recall of a schema only check (pydantic contract models) for one injected world."""
    texts, truth_rows = _render(world)
    types = {f.filename: f.feed_type for f in world.feeds}
    flagged: set[Unit] = set()
    for name, data in texts.items():
        if types[name] not in fault.feed_types:
            continue
        model = FEED_MODELS[types[name]]
        stream = io.StringIO(data.decode("utf-8"))
        parsed = open_text(name, stream)
        header_ok = True
        try:
            ProvenanceHeader.model_validate(parsed.header or {})
        except ValidationError:
            header_ok = False
        if not header_ok:
            flagged.add((name,))
        for row, text in enumerate(parsed.rows, 1):
            try:
                model.model_validate(json.loads(text))
            except (ValidationError, json.JSONDecodeError):
                record = json.loads(text) if text.startswith("{") else {}
                flagged.add((name, str(row)))
                station = record.get("station_id") if isinstance(record, dict) else None
                if isinstance(station, str):
                    flagged.add((name, station))
                flagged.add((name,))
    truth = truth_units(fault, truth_rows)
    if fault.unit == "record":
        flagged = {u for u in flagged if len(u) == 2 and u[1].isdigit()}
    elif fault.unit == "series":
        flagged = {u for u in flagged if len(u) == 2 and not u[1].isdigit()}
    else:
        flagged = {u for u in flagged if len(u) == 1}
    return _scores(truth, flagged)


def combined(seed: int, clean: World) -> dict[str, dict[str, float]]:
    """Every fault at 5 percent at once, every rule; precision against any fault."""
    broken = inject(clean, dict.fromkeys(sorted(FAULTS), COMBINED_RATE), seed=seed * 1000 + 999)
    texts, truth_rows = _render(broken)
    result = run_validation([Source.from_bytes(n, b) for n, b in texts.items()])
    try:
        found = result.all_findings()
        station_rows: dict[tuple[str, str], set[str]] = {}
        for feed in result.validated():
            if feed.feed_type != "traffic_counts":
                continue
            frame = result.con.execute(
                f"SELECT _row, station_id FROM {feed.table} WHERE station_id IS NOT NULL"
            ).df()
            for row, station in zip(frame["_row"], frame["station_id"], strict=True):
                station_rows.setdefault((feed.file, str(station)), set()).add(str(int(row)))
    finally:
        result.close()
    any_record: set[Unit] = set()
    any_series: set[Unit] = set()
    any_file: set[Unit] = set()
    for r in truth_rows:
        if r["unit"] == "record":
            any_record.add((r["file"], str(r["row"])))
        elif r["unit"] == "series":
            any_series.add((r["file"], str(r["series"])))
            for row in station_rows.get((r["file"], str(r["series"])), set()):
                any_record.add((r["file"], row))
        else:
            any_file.add((r["file"],))
    # A station or a file carries an injected fault when any of its rows does.
    row_station = {
        (file, row): station for (file, station), rows in station_rows.items() for row in rows
    }
    for file, row in any_record:
        any_file.add((file,))
        station = row_station.get((file, row))
        if station is not None:
            any_series.add((file, station))
    out = {}
    for fault_id, fault in sorted(FAULTS.items()):
        flagged = flagged_units(fault, found)
        truth = truth_units(fault, truth_rows)
        anything = {"record": any_record, "series": any_series, "file": any_file}[fault.unit]
        hits_any = len(flagged & anything)
        out[fault_id] = {
            "recall": len(truth & flagged) / len(truth) if truth else math.nan,
            "precision_any": hits_any / len(flagged) if flagged else math.nan,
        }
    return out


def run_seed(seed: int, rates: list[float], fault_ids: list[str]) -> dict[str, Any]:
    clean = build_world(WorldConfig(seed=seed))
    out: dict[str, Any] = {}
    baseline: dict[str, Any] = {}
    for i, fault_id in enumerate(fault_ids):
        for j, rate in enumerate(rates):
            broken = inject(clean, {fault_id: rate}, seed=seed * 1000 + i * 10 + j)
            out[f"{fault_id}|{rate}"] = score_fault(FAULTS[fault_id], broken)
            if rate == BASELINE_RATE:
                baseline[fault_id] = schema_baseline(FAULTS[fault_id], broken)
    return {
        "seed": seed,
        "runs": out,
        "schema_baseline": baseline,
        "combined": combined(seed, clean) if len(fault_ids) == len(FAULTS) else {},
    }


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
        entry: dict[str, Any] = {
            "title": fault.title,
            "unit": fault.unit,
            "expected_rules": list(fault.expected_rules),
            "by_rate": by_rate,
        }
        base = [
            s["schema_baseline"][fault_id] for s in per_seed if fault_id in s["schema_baseline"]
        ]
        if base:
            entry["schema_baseline_recall"] = _summary([b["recall"] for b in base])
        comb = [s["combined"][fault_id] for s in per_seed if s["combined"]]
        if comb:
            entry["combined"] = {
                "recall": _summary([c["recall"] for c in comb]),
                "precision_any": _summary([c["precision_any"] for c in comb]),
            }
        faults[fault_id] = entry
    return {
        "experiment": "E1",
        "title": "Fault detection by the conformance rules",
        "seeds": seeds,
        "rates": rates,
        "combined_rate": COMBINED_RATE,
        "baseline_rate": BASELINE_RATE,
        "faults": faults,
        "per_seed": per_seed,
    }
