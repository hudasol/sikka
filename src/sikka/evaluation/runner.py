"""Run experiments and write their results as stable JSON."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from sikka.conformance import SYNTHETIC_NOTICE
from sikka.core import round_floats, stable_json_dumps
from sikka.evaluation.e1 import run_e1
from sikka.evaluation.e2 import run_e2
from sikka.evaluation.e3 import run_e3
from sikka.evaluation.e4 import run_e4

EXPERIMENT_SEED_BASE = 2000
SMOKE_SEED = 1001
E1_RATES = [0.01, 0.05, 0.2]


def seed_list(n: int) -> list[int]:
    """The preregistered evaluation seeds: 2001, 2002, ... (n of them).

    Seed 1001 is the development and smoke seed. It is never part of the evaluation.
    """
    return [EXPERIMENT_SEED_BASE + i for i in range(1, n + 1)]


def undefined_to_null(value: Any) -> Any:
    """Undefined metrics (NaN, for example precision with nothing flagged) become null."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: undefined_to_null(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [undefined_to_null(v) for v in value]
    return value


def _write(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = undefined_to_null({"notice": SYNTHETIC_NOTICE, "generated_by": "sikka eval", **payload})
    path = out_dir / f"{name}.json"
    path.write_text(stable_json_dumps(round_floats(doc), indent=1) + "\n", encoding="utf-8")
    return path


def run_experiments(
    experiments: list[str], *, seeds: int, smoke: bool, workers: int, out_dir: Path
) -> list[Path]:
    written: list[Path] = []
    chosen = [SMOKE_SEED] if smoke else seed_list(seeds)
    for name in experiments:
        if name == "e1":
            rates = [0.05] if smoke else E1_RATES
            written.append(
                _write(out_dir, "e1_fault_detection", run_e1(chosen, rates, workers=workers))
            )
        elif name == "e2":
            scenarios = ["clean"] if smoke else None
            written.append(
                _write(out_dir, "e2_entity_resolution", run_e2(chosen, scenarios, workers=workers))
            )
        elif name == "e3":
            written.append(_write(out_dir, "e3_blackspot_ranking", run_e3(chosen, workers=workers)))
        elif name == "e4":
            written.append(_write(out_dir, "e4_robustness", run_e4(chosen, workers=workers)))
        else:
            raise ValueError(f"unknown experiment {name!r}")
    return written
