from __future__ import annotations

import importlib
import logging

import pytest
from typer.testing import CliRunner

import sikka.cli.main as cli_main
from sikka.cli import app
from sikka.cli.checks import Step, run_steps
from sikka.core import Paths, get_logger

LAYERS = [
    "sikka.core",
    "sikka.contract",
    "sikka.synth",
    "sikka.ingest",
    "sikka.conformance",
    "sikka.harmonise",
    "sikka.analytics",
    "sikka.tasking",
    "sikka.api",
    "sikka.evaluation",
    "sikka.cli",
]


@pytest.mark.parametrize("name", LAYERS)
def test_every_layer_exposes_a_public_interface(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__, f"{name} needs a docstring describing the layer"
    assert isinstance(module.__all__, list)


def test_logger_is_namespaced() -> None:
    log = get_logger("demo")
    assert log.name == "sikka.demo"
    assert get_logger("sikka.x").name == "sikka.x"
    assert logging.getLogger("sikka").handlers


def test_run_steps_reports_exit_codes() -> None:
    import sys

    root = Paths().root
    ok = Step("ok", [sys.executable, "-c", "pass"])
    bad = Step("bad", [sys.executable, "-c", "raise SystemExit(3)"])
    outcomes = run_steps([ok, bad], root)
    assert [(n, c) for n, c, _ in outcomes] == [("ok", 0), ("bad", 3)]


def test_check_command_summarises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "run_steps", lambda steps, root: [("ruff lint", 0, 0.1)])
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "sikka check passed" in result.stdout

    monkeypatch.setattr(cli_main, "run_steps", lambda steps, root: [("pytest", 1, 0.1)])
    result = CliRunner().invoke(app, ["check", "--no-coverage"])
    assert result.exit_code == 1
    assert "FAILED" in result.stdout
