from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sikka.evaluation.runner as runner
from sikka.cli import app
from sikka.evaluation import run_experiments, seed_list


def test_seed_list_is_preregistered() -> None:
    assert seed_list(3) == [1001, 1002, 1003]


def test_unknown_experiment(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown experiment"):
        run_experiments(["e9"], seeds=1, smoke=True, workers=1, out_dir=tmp_path)


def test_results_are_written_with_the_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(seeds: list[int], rates: list[float], workers: int = 1) -> dict[str, Any]:
        return {"experiment": "E1", "seeds": seeds, "rates": rates, "value": 1 / 3}

    monkeypatch.setattr(runner, "run_e1", fake)
    (path,) = run_experiments(["e1"], seeds=2, smoke=False, workers=1, out_dir=tmp_path)
    doc = json.loads(path.read_text("utf-8"))
    assert doc["notice"].startswith("Synthetic data.")
    assert doc["seeds"] == [1001, 1002]
    assert doc["rates"] == [0.01, 0.05, 0.2]
    assert doc["value"] == 0.333333


def test_eval_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sikka.evaluation as evaluation

    calls: dict[str, Any] = {}

    def fake(experiments: list[str], **kwargs: Any) -> list[Path]:
        calls.update(kwargs, experiments=experiments)
        return []

    monkeypatch.setattr(evaluation, "run_experiments", fake)
    result = CliRunner().invoke(app, ["eval", "--smoke", "--experiments", "E1"])
    assert result.exit_code == 0, result.stdout
    assert calls["experiments"] == ["e1"]
    assert calls["seeds"] == 1
    assert calls["smoke"] is True
