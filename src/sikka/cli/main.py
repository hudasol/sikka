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
from sikka.core import DEFAULT_SEED, Paths, stable_json_dumps, write_text_lf
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
    write_text_lf(stem.with_suffix(".json"), stable_json_dumps(report, indent=1) + "\n")
    write_text_lf(stem.with_suffix(".html"), render_html(report))
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


@app.command("eval")
def evaluate(
    experiments: str = typer.Option("e1,e2,e3,e4,e5", help="Comma separated experiments to run."),
    seeds: int = typer.Option(20, help="Number of seeds (1 to N)."),
    smoke: bool = typer.Option(False, help="One seed and one rate, written to build/."),
    workers: int = typer.Option(4, help="Worker processes."),
) -> None:
    """Run the preregistered evaluation and write results/*.json."""
    from sikka.evaluation import run_experiments

    paths = Paths()
    out = paths.build / "eval-smoke" if smoke else paths.results
    written = run_experiments(
        [e.strip().lower() for e in experiments.split(",") if e.strip()],
        seeds=1 if smoke else seeds,
        smoke=smoke,
        workers=workers,
        out_dir=out,
    )
    for path in written:
        typer.echo(f"wrote {path.relative_to(paths.root).as_posix()}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Interface to bind."),
    port: int = typer.Option(8000, help="Port of the live API."),
) -> None:
    """Start the live API (FastAPI under uvicorn)."""
    import uvicorn

    from sikka.api import Service, create_app

    paths = Paths()
    service = Service(paths=paths, store_dir=paths.build / "api-reports")
    typer.echo("Synthetic data. No real crash, traffic or road records are used.")
    uvicorn.run(create_app(service), host=host, port=port, log_level="info")


@app.command()
def snapshot() -> None:
    """Precompute every API response into web/public/snapshot for the static demo."""
    from sikka.api import Service, snapshot_files

    paths = Paths()
    files = snapshot_files(Service(paths=paths, mode="static"))
    written = write_artefacts(paths.root, files)
    size = sum(len(text.encode("utf-8")) for text in files.values())
    typer.echo(f"snapshot: {len(files)} files, {size // 1024} KB, {len(written)} updated")


@app.command()
def harmonise(
    dataset: str = typer.Option("broken", help="Sample set to harmonise: clean or broken."),
    out: Path = typer.Option(Path("build/harmonised"), help="Output folder."),
) -> None:
    """Harmonise a sample set into the canonical model and write it with lineage."""
    from sikka.api import Service

    service = Service(paths=Paths())
    ds = service.dataset(dataset)
    out.mkdir(parents=True, exist_ok=True)
    docs = {
        "crashes": [c.as_dict() for c in ds.crashes],
        "exposure": [e.as_dict() for e in ds.exposure.values()],
        "decisions": [d.as_dict() for d in ds.decisions],
        "lineage": ds.lineage_index(),
        "summary": ds.resolution_summary(),
    }
    for name, doc in docs.items():
        write_text_lf(out / f"{name}.json", stable_json_dumps(doc, indent=1) + "\n")
    summary = docs["summary"]
    typer.echo("Synthetic data. No real crash, traffic or road records are used.")
    typer.echo(
        f"{summary['producer_records']} producer records -> {summary['canonical_crashes']} "
        f"canonical crashes; pairs: {summary['match']} match, {summary['non_match']} non match, "
        f"{summary['unresolved']} unresolved; written to {out}"
    )


@app.command()
def perf() -> None:
    """Measure the performance budgets and write results/performance.json."""
    from sikka.evaluation.performance import measure

    paths = Paths()
    doc = measure(paths)
    paths.results.mkdir(parents=True, exist_ok=True)
    write_text_lf(paths.results / "performance.json", stable_json_dumps(doc, indent=1) + "\n")
    for m in doc["measures"]:
        typer.echo(f"{m['name']}: {m['value']} (budget {m['budget']})")


@app.command("all")
def run_all(
    evaluation: bool = typer.Option(
        True, help="Run the full evaluation (several hours on a laptop)."
    ),
    workers: int = typer.Option(3, help="Worker processes for the evaluation."),
) -> None:
    """Regenerate every artefact: samples, docs, evaluation, performance, snapshot, check."""
    import subprocess

    paths = Paths()
    steps: list[tuple[str, list[str]]] = [
        ("generate", ["generate"]),
        ("docs build", ["docs", "build"]),
    ]
    if evaluation:
        steps.append(("eval", ["eval", "--workers", str(workers)]))
    steps += [
        ("perf", ["perf"]),
        ("docs build", ["docs", "build"]),
        ("snapshot", ["snapshot"]),
        ("check", ["check"]),
    ]
    for name, args in steps:
        typer.echo(f"==> sikka {name}")
        code = subprocess.call([sys.executable, "-m", "sikka.cli", *args], cwd=paths.root)
        if code != 0:
            typer.echo(f"sikka {name} failed with exit code {code}", err=True)
            raise typer.Exit(code)
    typer.echo("sikka all finished; build the web app with: npm --prefix web run build")
