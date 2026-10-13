"""Command line entry point: ``sikka``."""

from __future__ import annotations

import json
import sys

import typer

from sikka import __version__
from sikka.cli.checks import fast_check_steps, run_steps
from sikka.cli.docs import collect_artefacts, stale_artefacts, write_artefacts
from sikka.contract import diff_versions, render_diff_text, resolve_version
from sikka.core import Paths

app = typer.Typer(
    name="sikka",
    help="Sikka: data contract checker and blackspot ranking for road feeds. Synthetic data only.",
    no_args_is_help=True,
    add_completion=False,
)
contract_app = typer.Typer(help="Inspect and compare contract versions.", no_args_is_help=True)
docs_app = typer.Typer(help="Generated documentation and artefacts.", no_args_is_help=True)
app.add_typer(contract_app, name="contract")
app.add_typer(docs_app, name="docs")


@app.callback()
def _utf8_output() -> None:
    """Arabic text must print on Windows consoles that default to a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


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


@contract_app.command("diff")
def contract_diff(
    old: str = typer.Argument(..., help="Old version, for example v1 or 1.0.0."),
    new: str = typer.Argument(..., help="New version, for example v1.1 or 1.1.0."),
    as_json: bool = typer.Option(False, "--json", help="Print the diff as JSON."),
) -> None:
    """Compare two contract versions and check the versioning rule."""
    try:
        diff = diff_versions(resolve_version(old), resolve_version(new))
    except KeyError as exc:
        typer.echo(str(exc.args[0]), err=True)
        raise typer.Exit(2) from exc
    if as_json:
        typer.echo(json.dumps(diff.as_dict(), indent=2))
    else:
        typer.echo(render_diff_text(diff))
    if not diff.compatible:
        raise typer.Exit(1)


@docs_app.command("build")
def docs_build(
    check_only: bool = typer.Option(False, "--check", help="Fail if any artefact is stale."),
) -> None:
    """Regenerate schemas, field dictionary, rule catalogue and TypeScript types."""
    root = Paths().root
    files = collect_artefacts()
    if check_only:
        stale = stale_artefacts(root, files)
        for rel in stale:
            typer.echo(f"stale: {rel}")
        if stale:
            raise typer.Exit(1)
        typer.echo(f"{len(files)} generated artefacts are fresh")
        return
    written = write_artefacts(root, files)
    for rel in written:
        typer.echo(f"wrote {rel}")
    typer.echo(f"{len(written)} of {len(files)} artefacts updated")
