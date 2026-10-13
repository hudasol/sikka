from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sikka.cli import app
from sikka.conformance import (
    REGISTRY,
    Source,
    build_report,
    render_html,
    report_id,
    rules_by_field,
    run_validation,
)
from sikka.evaluation.e1 import run_e1, score_fault
from sikka.synth import CATALOGUE, FAULTS, WorldConfig, build_world, inject

from .helpers import CLEAN, ROOT, crash_like, feed_bytes, registry_source

BROKEN = ROOT / "data" / "samples" / "broken"
HERE = Path(__file__).parent


def test_every_fault_is_caught_by_registered_rules() -> None:
    for fault in CATALOGUE:
        assert fault.expected_rules, fault.id
        for rule_id in fault.expected_rules:
            assert rule_id in REGISTRY, f"{fault.id} expects unknown rule {rule_id}"


def test_every_rule_has_a_test() -> None:
    covered_by_examples = {r.id for r in REGISTRY.values() if r.example is not None}
    text = (HERE / "test_series_and_cross_rules.py").read_text("utf-8")
    covered_by_name = set(re.findall(r"test_([a-z]\d{3})_", text))
    for rule in REGISTRY.values():
        short = rule.id[3:].lower()
        assert rule.id in covered_by_examples or short in covered_by_name, rule.id


def test_rules_by_field_expands_wildcards() -> None:
    mapping = rules_by_field()
    assert "SK-S005" in mapping["crash_records.crash_id"]
    assert "SK-V004" in mapping["crash_records.lat"]


@pytest.fixture(scope="module")
def broken_report() -> dict:  # type: ignore[type-arg]
    sources = [Source.from_path(BROKEN / "crash_records_producer_b.ndjson")]
    refs = [Source.from_path(p) for p in sorted(CLEAN.iterdir()) if "producer_b" not in p.name]
    result = run_validation(sources, refs)
    try:
        report = build_report(result)
        assert report["report_id"] == report_id(result)
    finally:
        result.close()
    return report


def test_report_structure(broken_report: dict) -> None:  # type: ignore[type-arg]
    assert broken_report["notice"].startswith("Synthetic data.")
    assert broken_report["report_id"].startswith("RPT-")
    assert {f["family"] for f in broken_report["families"]} == set("SVRXTP")
    failing = {r["rule_id"] for r in broken_report["rules"] if r["findings"] > 0}
    assert {"SK-S008", "SK-V004", "SK-P001", "SK-X001"} <= failing
    for rule in broken_report["rules"]:
        assert len(rule["examples"]) <= 5
        assert 0.0 <= rule["share"] <= 1.0
    scores = [s for s in broken_report["scores"] if s["producer_id"] == "PRODUCER_B"]
    assert {s["family"] for s in scores} == set("SVRXTP") | {"ALL"}
    for s in scores:
        assert s["low"] <= s["estimate"] <= s["high"]


def test_quarantined_values_never_reach_the_report(broken_report: dict) -> None:  # type: ignore[type-arg]
    text = render_html(broken_report) + str(broken_report)
    assert "Synthetic Person" not in text
    assert "SYN 00000" not in text
    assert "+97150" not in text
    assert "784-1900" not in text
    quarantined = next(f for f in broken_report["files"])["quarantined_rows"]
    assert quarantined > 0


def test_report_id_is_idempotent() -> None:
    data = feed_bytes("crash_records", [crash_like(1)])
    ids = []
    for _ in range(2):
        result = run_validation([Source.from_bytes("x.ndjson", data)], [registry_source()])
        ids.append(report_id(result))
        result.close()
    assert ids[0] == ids[1]
    other = feed_bytes("crash_records", [crash_like(2)])
    result = run_validation([Source.from_bytes("x.ndjson", other)], [registry_source()])
    assert report_id(result) != ids[0]
    result.close()


def test_html_report_is_self_contained(broken_report: dict) -> None:  # type: ignore[type-arg]
    html = render_html(broken_report)
    assert "<script" not in html
    assert "http://" not in html.replace("http://www.w3", "")
    assert "@media print" in html
    assert "Synthetic data. No real crash, traffic or road records are used." in html


def test_unknown_feed_runs_header_rules_only() -> None:
    result = run_validation([Source.from_bytes("x.ndjson", b'{"x": 1}\n')])
    statuses = {o.rule.id: o.status for o in result.outcomes}
    result.close()
    assert statuses["SK-S001"] == "evaluated"
    assert statuses["SK-V001"] == "not_applicable"


def test_rules_needing_a_registry_are_skipped_without_one() -> None:
    result = run_validation(
        [Source.from_bytes("x.ndjson", feed_bytes("crash_records", [crash_like(1)]))]
    )
    skipped = {o.rule.id: o.note for o in result.outcomes if o.status == "skipped"}
    result.close()
    assert "SK-R001" in skipped
    assert "registry" in skipped["SK-R001"]


def test_cli_validate_writes_reports(tmp_path: Path) -> None:
    runner = CliRunner()
    target = BROKEN / "road_segments_producer_c.geojson"
    result = runner.invoke(app, ["validate", str(target), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "Synthetic data." in result.stdout
    assert len(list(tmp_path.glob("RPT-*.json"))) == 1
    assert len(list(tmp_path.glob("RPT-*.html"))) == 1
    missing = runner.invoke(app, ["validate", str(tmp_path / "nope.csv")])
    assert missing.exit_code == 2


def test_e1_smoke_on_a_small_world() -> None:
    small = build_world(WorldConfig(seed=31, segments_per_corridor=8, target_total_crashes=700))
    for fault_id in ("F01", "F11", "F24"):
        scores = score_fault(FAULTS[fault_id], inject(small, {fault_id: 0.05}, seed=1))
        assert scores["truth"] > 0
        assert scores["recall"] == 1.0
        assert scores["precision"] == 1.0


@pytest.mark.slow
def test_e1_runner_aggregates_seeds() -> None:
    out = run_e1([5], [0.05], ["F01"])
    summary = out["faults"]["F01"]["by_rate"]["0.05"]
    assert summary["recall"]["n"] == 1


def test_personal_values_inside_contract_fields_are_quarantined_everywhere() -> None:
    """Regression from the independent review: a phone number in an enum or id field."""
    import json

    from sikka.harmonise import harmonise

    phone_a, phone_b = "+971501234567", "+971501234568"
    records = [
        crash_like(1, weather=phone_a),
        crash_like(2) | {"crash_id": phone_b},
        crash_like(3),
    ]
    data = feed_bytes("crash_records", records)
    result = run_validation([Source.from_bytes("pii.ndjson", data)], [registry_source()])
    try:
        assert result.quarantined("pii.ndjson") == {1, 2}
        report = build_report(result)
    finally:
        result.close()
    text = json.dumps(report) + render_html(report)
    assert phone_a not in text
    assert phone_b not in text
    ds = harmonise([Source.from_bytes("pii.ndjson", data)], [registry_source()])
    lineage = json.dumps(ds.lineage_index())
    assert phone_a not in lineage
    assert phone_b not in lineage


def test_every_rule_and_fault_has_an_arabic_title() -> None:
    from sikka.conformance import FAULT_TITLES_AR, TITLES_AR

    assert set(TITLES_AR) == set(REGISTRY)
    assert set(FAULT_TITLES_AR) == {f.id for f in CATALOGUE}
    for title in [*TITLES_AR.values(), *FAULT_TITLES_AR.values()]:
        assert any("ء" <= ch <= "ي" for ch in title)


def test_files_not_declared_synthetic_change_the_notice() -> None:
    data = feed_bytes("crash_records", [crash_like(1)], synthetic=False)
    result = run_validation([Source.from_bytes("real.ndjson", data)], [registry_source()])
    try:
        report = build_report(result)
    finally:
        result.close()
    assert report["files_not_declared_synthetic"] == ["real.ndjson"]
    assert "must not be used here" in report["notice"]
    for rule in report["rules"]:
        assert rule["share_low"] <= rule["share"] <= rule["share_high"]
