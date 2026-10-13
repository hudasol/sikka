"""The machine checkable predictions repeat the preregistration word for word."""

from __future__ import annotations

import re

from sikka.core import Paths
from sikka.evaluation.predictions import PREDICTIONS, judge


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_every_prediction_matches_the_preregistration() -> None:
    prereg = _norm((Paths().root / "docs" / "PREREGISTRATION.md").read_text("utf-8"))
    for p in PREDICTIONS:
        assert _norm(f"{p.id}: {p.text}") in prereg, p.id


def test_prediction_ids_are_unique_and_complete() -> None:
    ids = [p.id for p in PREDICTIONS]
    assert len(ids) == len(set(ids))
    prereg = (Paths().root / "docs" / "PREREGISTRATION.md").read_text("utf-8")
    registered = set(re.findall(r"\bP([1-5])\.(\d+):", prereg))
    assert {tuple(i[1:].split(".")) for i in ids} == registered


def test_missing_results_are_pending() -> None:
    verdicts = judge({})
    assert {v["verdict"] for v in verdicts} == {"PENDING"}
