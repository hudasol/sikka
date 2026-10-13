"""Run experiments and write their results as stable JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sikka.conformance import SYNTHETIC_NOTICE
from sikka.core import round_floats, stable_json_dumps
from sikka.evaluation.e1 import run_e1

EXPERIMENT_SEED_BASE = 1000
E1_RATES = [0.01, 0.05, 0.2]


def seed_list(n: int) -> list[int]:
    """The preregistered seeds: 1001, 1002, ... (n of them)."""
    return [EXPERIMENT_SEED_BASE + i for i in range(1, n + 1)]


def _write(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"notice": SYNTHETIC_NOTICE, "generated_by": "sikka eval", **payload}
    path = out_dir / f"{name}.json"
    path.write_text(stable_json_dumps(round_floats(doc), indent=1) + "\n", encoding="utf-8")
    return path


def run_experiments(
    experiments: list[str], *, seeds: int, smoke: bool, workers: int, out_dir: Path
) -> list[Path]:
    written: list[Path] = []
    chosen = seed_list(seeds)
    for name in experiments:
        if name == "e1":
            rates = [0.05] if smoke else E1_RATES
            written.append(
                _write(out_dir, "e1_fault_detection", run_e1(chosen, rates, workers=workers))
            )
        else:
            raise ValueError(f"unknown experiment {name!r}")
    return written
