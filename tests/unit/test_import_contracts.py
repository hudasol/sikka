"""The layer order in the import contracts must match the architecture."""

from __future__ import annotations

import tomllib
from typing import cast

from sikka.core import Paths

EXPECTED = [
    "sikka.cli",
    "sikka.evaluation",
    "sikka.api",
    "sikka.tasking",
    "sikka.analytics",
    "sikka.harmonise",
    "sikka.conformance",
    "sikka.ingest",
    "sikka.synth",
    "sikka.contract",
    "sikka.core",
]


def _contracts() -> list[dict[str, object]]:
    data = tomllib.loads((Paths().root / "pyproject.toml").read_text(encoding="utf-8"))
    contracts: list[dict[str, object]] = data["tool"]["importlinter"]["contracts"]
    return contracts


def test_layers_contract_matches_architecture() -> None:
    layers = [c for c in _contracts() if c["type"] == "layers"]
    assert len(layers) == 1
    assert layers[0]["layers"] == EXPECTED


def test_product_layers_cannot_read_synthetic_truth() -> None:
    forbidden = [c for c in _contracts() if c["type"] == "forbidden"]
    product = {"sikka.conformance", "sikka.analytics", "sikka.api"}
    assert any(
        c["forbidden_modules"] == ["sikka.synth"]
        and product <= set(cast("list[str]", c["source_modules"]))
        for c in forbidden
    )
