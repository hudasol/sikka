from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from sikka.cli import app
from sikka.cli.docs import collect_artefacts, stale_artefacts, write_artefacts
from sikka.contract import (
    FEED_MODELS,
    VERSIONS,
    ContractVersion,
    contract_bundle,
    diff_versions,
    render_diff_text,
    render_typescript,
    resolve_version,
)
from sikka.contract.models import TrafficCount, describe
from sikka.core import Paths

runner = CliRunner()


def test_generated_artefacts_are_fresh() -> None:
    stale = stale_artefacts(Paths().root, collect_artefacts())
    assert not stale, f"run `sikka docs build`; stale: {stale}"


def test_write_and_staleness_helpers(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    files = {"a/b.txt": "x\n"}
    assert stale_artefacts(root, files) == ["a/b.txt"]
    assert write_artefacts(root, files) == ["a/b.txt"]
    assert write_artefacts(root, files) == []
    assert stale_artefacts(root, files) == []


def test_resolve_aliases() -> None:
    assert resolve_version("v1").version == "1.0.0"
    assert resolve_version("1.1.0").version == "1.1.0"
    assert resolve_version("v1.1.0").version == "1.1.0"
    with pytest.raises(KeyError, match="unknown contract version"):
        resolve_version("v9")


def test_minor_draft_is_compatible() -> None:
    diff = diff_versions(VERSIONS["1.0.0"], VERSIONS["1.1.0"])
    assert [(c.feed, c.field, c.kind, c.impact) for c in diff.changes] == [
        ("crash_records", "work_zone", "added", "minor")
    ]
    assert diff.required_bump == "minor"
    assert diff.compatible


def test_removal_is_major_and_flagged() -> None:
    diff = diff_versions(VERSIONS["1.1.0"], VERSIONS["1.0.0"])
    assert diff.required_bump == "major"
    assert not diff.compatible
    assert "Compatible with the versioning rule: no" in render_diff_text(diff)


def test_identical_versions_have_no_changes() -> None:
    diff = diff_versions(VERSIONS["1.0.0"], VERSIONS["1.0.0"])
    assert diff.changes == []
    assert diff.required_bump is None
    assert diff.declared_bump is None
    assert diff.compatible
    assert "No changes." in render_diff_text(diff)


class _TrafficCountUnitChange(TrafficCount):
    mean_speed_kmh: float = describe(
        "Mean spot speed of counted vehicles, reworded.",
        "متوسط السرعة.",
        example=29.0,
        unit="m/s",
        ge=0,
        le=70,
    )


def test_unit_change_needs_major_bump() -> None:
    changed = ContractVersion(
        version="1.2.0",
        status="draft",
        summary="test",
        feeds={**FEED_MODELS, "traffic_counts": _TrafficCountUnitChange},
    )
    diff = diff_versions(VERSIONS["1.0.0"], changed)
    impacts = {c.detail.split(":")[0]: c.impact for c in diff.changes}
    assert impacts["unit"] == "major"
    assert impacts["allowed"] == "major"
    assert impacts["description_en reworded"] == "patch"
    assert not diff.compatible
    assert diff.declared_bump == "minor"
    patch = ContractVersion("2.0.0", "draft", "t", changed.feeds)
    assert diff_versions(VERSIONS["1.0.0"], patch).compatible


def test_bundle_lists_prohibited_fields_and_header() -> None:
    bundle = contract_bundle(VERSIONS["1.0.0"])
    assert bundle["synthetic_only_repository"] is True
    assert "plate_number" in bundle["prohibited_fields"]
    assert set(bundle["feeds"]) == {
        "provenance_header",
        "road_segments",
        "crash_records",
        "traffic_counts",
    }
    names = [f["name"] for f in bundle["feeds"]["traffic_counts"]["fields"]]
    assert "class_counts.heavy_goods" in names


def test_typescript_has_interfaces_for_current_version_only() -> None:
    ts = render_typescript()
    for name in ("ProvenanceHeader", "RoadSegment", "CrashRecord", "TrafficCount"):
        assert f"export interface {name} " in ts
    assert "work_zone" not in ts
    assert "readonly class_counts?:" in ts
    assert "Array<[number, number]>" in ts


def test_cli_contract_diff() -> None:
    ok = runner.invoke(app, ["contract", "diff", "v1", "v1.1"])
    assert ok.exit_code == 0
    assert "work_zone" in ok.stdout
    bad = runner.invoke(app, ["contract", "diff", "v1.1", "v1", "--json"])
    assert bad.exit_code == 1
    assert json.loads(bad.stdout)["compatible"] is False
    unknown = runner.invoke(app, ["contract", "diff", "v1", "v7"])
    assert unknown.exit_code == 2


def test_cli_docs_build_check() -> None:
    result = runner.invoke(app, ["docs", "build", "--check"])
    assert result.exit_code == 0, result.stdout
    assert "fresh" in result.stdout
