from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sikka.cli import app
from sikka.core import rng
from sikka.synth import CATALOGUE, FAULTS, WorldConfig, build_world, inject, write_world
from sikka.synth.faults import _pick

SMALL = WorldConfig(seed=21, segments_per_corridor=8, target_total_crashes=700.0)
CLEAN = build_world(SMALL)


def test_catalogue_is_complete() -> None:
    assert [f.id for f in CATALOGUE] == [f"F{i:02d}" for i in range(1, 26)]
    for fault in CATALOGUE:
        assert fault.expected_rules, fault.id
        assert all(re.fullmatch(r"SK-[SVRXTP]\d{3}", r) for r in fault.expected_rules)
        assert fault.unit in {"record", "series", "file"}
        assert 0 < fault.default_rate <= 1
        assert fault.as_dict()["id"] == fault.id


def test_pick_always_selects_at_least_one() -> None:
    gen = rng(1, "t")
    assert _pick(gen, 0, 0.5) == []
    assert len(_pick(gen, 10, 0.0)) == 1
    assert len(_pick(gen, 10, 1.0)) == 10


@pytest.fixture(scope="module")
def clean_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("clean")
    write_world(CLEAN, out)
    return out


@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_each_fault_is_logged_and_changes_the_feeds(
    fault_id: str, tmp_path: Path, clean_dir: Path
) -> None:
    broken = inject(CLEAN, {fault_id: 0.05}, seed=3)
    assert broken.injected == {fault_id: 0.05}
    write_world(broken, tmp_path)
    faults = json.loads((tmp_path / "ground_truth" / "faults.json").read_text("utf-8"))
    logged = [r for r in faults if r["fault_id"] == fault_id]
    assert logged, f"{fault_id} left no ground truth"
    if fault_id != "F20":
        assert {r["unit"] for r in logged} == {FAULTS[fault_id].unit}
    changed = [
        p.name
        for p in sorted((clean_dir / "feeds").iterdir())
        if p.read_bytes() != (tmp_path / "feeds" / p.name).read_bytes()
    ]
    assert changed, f"{fault_id} did not change any feed"
    # The clean world is untouched by injection.
    assert CLEAN.injected == {}


def test_injection_is_deterministic(tmp_path: Path) -> None:
    rates = {f.id: 0.03 for f in CATALOGUE}
    write_world(inject(CLEAN, rates, seed=9), tmp_path / "a")
    write_world(inject(CLEAN, rates, seed=9), tmp_path / "b")
    for path in sorted((tmp_path / "a").rglob("*")):
        if path.is_file():
            assert (
                path.read_bytes()
                == (tmp_path / "b" / path.relative_to(tmp_path / "a")).read_bytes()
            )


def test_specific_fault_effects() -> None:
    w = inject(CLEAN, {"F05": 0.2, "F25": 1.0, "F24": 1.0}, seed=4)
    sev = [r["severity"] for f in w.feeds if f.feed_type == "crash_records" for r in f.records]
    assert any(isinstance(s, int) and 1 <= s <= 3 for s in sev)
    assert all(f.header["synthetic"] is False for f in w.feeds)
    assert all("record_count_override" in f.header for f in w.feeds)


def test_bad_rate_is_refused() -> None:
    with pytest.raises(ValueError, match="rate"):
        inject(CLEAN, {"F01": 0.0}, seed=1)


def test_generate_command(tmp_path: Path) -> None:
    out = tmp_path / "w"
    runner = CliRunner()
    bad = runner.invoke(app, ["generate", "--faults", "F99", "--no-samples"])
    assert bad.exit_code == 2
    import os

    os.environ["SIKKA_ROOT"] = str(tmp_path)
    try:
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        result = runner.invoke(
            app,
            ["generate", "--seed", "4", "--faults", "F01", "--out", "w", "--no-samples"],
        )
    finally:
        del os.environ["SIKKA_ROOT"]
    assert result.exit_code == 0, result.stdout
    assert (out / "ground_truth" / "faults.json").is_file()
