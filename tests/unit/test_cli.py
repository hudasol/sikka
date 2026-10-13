from __future__ import annotations

from typer.testing import CliRunner

from sikka import __version__
from sikka.cli import app
from sikka.cli.checks import fast_check_steps

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_fast_check_covers_every_gate() -> None:
    names = [step.name for step in fast_check_steps()]
    assert names == ["ruff lint", "ruff format", "mypy strict", "import contracts", "pytest"]
    pytest_step = fast_check_steps()[-1].argv
    assert "--cov-fail-under=85" in pytest_step
    assert all("--cov" not in a for a in fast_check_steps(with_coverage=False)[-1].argv)
