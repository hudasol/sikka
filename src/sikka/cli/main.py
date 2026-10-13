"""Command line entry point: ``sikka``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from sikka import __version__
from sikka.cli.checks import fast_check_steps, run_steps
from sikka.cli.docs import collect_artefacts, stale_artefacts, write_artefacts
from sikka.conformance import Source, build_report, render_html, run_validation
from sikka.contract import diff_versions, render_diff_text, resolve_version
from sikka.core import DEFAULT_SEED, Paths, stable_json_dumps
from sikka.synth import FAULTS, WorldConfig, build_world, inject, sample_files, write_world

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


@app.command()
def generate(
    seed: int = typer.Option(DEFAULT_SEED, help="Seed of the synthetic world."),
    faults: str = typer.Option("", help="Comma separated fault ids to inject, or 'all'."),
    rate: float = typer.Option(0.05, help="Injection rate for the chosen faults."),
    out: str = typer.Option("", help="Output folder. Default: build/world-SEED."),
    samples: bool = typer.Option(True, help="Also rewrite the committed sample feeds."),
) -> None:
    """Generate a synthetic world with feeds and a hidden ground truth sidecar."""
    paths = Paths()
    chosen = sorted(FAULTS) if faults == "all" else [f for f in faults.split(",") if f]
    unknown = [f for f in chosen if f not in FAULTS]
    if unknown:
        typer.echo(f"unknown fault ids: {unknown}", err=True)
        raise typer.Exit(2)
    world = build_world(WorldConfig(seed=seed))
    if chosen:
        world = inject(world, dict.fromkeys(chosen, rate), seed)
    target = paths.root / (out or f"build/world-{seed}")
    written = write_world(world, target)
    typer.echo(
        f"synthetic world seed {seed}: {len(written)} files in {target.relative_to(paths.root)}"
    )
    if samples:
        updated = write_artefacts(paths.root, sample_files())
        typer.echo(f"sample feeds: {len(updated)} files updated")


@app.command()
def validate(
    files: list[Path] = typer.Argument(..., help="Feed files to validate."),
    context: str = typer.Option(
        "samples", help="Reference feeds for cross feed rules: 'samples' or 'none'."
    ),
    out: Path = typer.Option(Path("build/reports"), help="Folder for the JSON and HTML report."),
) -> None:
    """Validate feeds against the contract and write a JSON and an HTML report."""
    paths = Paths()
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        typer.echo(f"not found: {missing}", err=True)
        raise typer.Exit(2)
    names = {f.name for f in files}
    references: list[Source] = []
    if context == "samples":
        clean = paths.samples / "clean"
        references = [
            Source.from_path(p)
            for p in sorted(clean.iterdir())
            if p.is_file() and p.name not in names
        ]
    result = run_validation([Source.from_path(f) for f in files], references)
    try:
        report = build_report(result)
    finally:
        result.close()
    out.mkdir(parents=True, exist_ok=True)
    stem = out / report["report_id"]
    stem.with_suffix(".json").write_text(stable_json_dumps(report, indent=1) + "\n", "utf-8")
    stem.with_suffix(".html").write_text(render_html(report), "utf-8")
    typer.echo(report["notice"])
    for fam in report["families"]:
        typer.echo(
            f"{fam['family']} {fam['name']:<28} rules failing {fam['rules_failing']:>2}  "
            f"findings {fam['findings']}"
        )
    for s in report["scores"]:
        if s["family"] == "ALL":
            typer.echo(
                f"{s['producer_id']}: {100 * s['estimate']:.1f} percent of records pass every "
                f"family (95 percent interval {100 * s['low']:.1f} to {100 * s['high']:.1f})"
            )
    typer.echo(f"report {report['report_id']} written to {out}")
