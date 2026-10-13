"""Command line entry point: ``sikka``."""

from __future__ import annotations

import typer

from sikka import __version__
from sikka.cli.checks import fast_check_steps, run_steps
from sikka.core import Paths

app = typer.Typer(
    name="sikka",
    help="Sikka: data contract checker and blackspot ranking for road feeds. Synthetic data only.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def check(
    coverage: bool = typer.Option(True, help="Enforce the coverage floor during tests."),
) -> None:
    """Fast check: lint, format, strict types, import contracts and unit tests."""
    paths = Paths()
    outcomes = run_steps(fast_check_steps(with_coverage=coverage), paths.root)
    typer.echo("")
    failed = False
    for name, code, seconds in outcomes:
        status = "ok" if code == 0 else f"FAILED ({code})"
        typer.echo(f"{name:<18} {status:<12} {seconds:6.1f}s")
        failed = failed or code != 0
    if failed:
        raise typer.Exit(1)
    typer.echo("sikka check passed")
