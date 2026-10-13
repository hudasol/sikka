"""Contract versions. 1.0.0 is released; 1.1.0 is a draft that adds one optional field."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sikka.contract.models import (
    FEED_MODELS,
    ContractModel,
    CrashRecord,
    ProvenanceHeader,
    describe,
)


class CrashRecordV110(CrashRecord):
    """Crash record in draft 1.1.0: adds the optional ``work_zone`` flag."""

    work_zone: bool | None = describe(
        "True when the crash occurred inside a marked road works zone. Absent when unknown.",
        "تكون القيمة صحيحة إذا وقع الحادث داخل منطقة أعمال طرق محددة. يُحذف الحقل عند عدم المعرفة.",
        example=False,
        default=None,
    )


@dataclass(frozen=True)
class ContractVersion:
    version: str
    status: Literal["released", "draft"]
    summary: str
    feeds: dict[str, type[ContractModel]]
    header: type[ContractModel] = ProvenanceHeader


VERSIONS: dict[str, ContractVersion] = {
    "1.0.0": ContractVersion(
        version="1.0.0",
        status="released",
        summary="First contract: road segment registry, crash records and traffic station counts.",
        feeds=dict(FEED_MODELS),
    ),
    "1.1.0": ContractVersion(
        version="1.1.0",
        status="draft",
        summary="Draft: adds the optional work_zone flag to crash records.",
        feeds={**FEED_MODELS, "crash_records": CrashRecordV110},
    ),
}

CURRENT_VERSION = "1.0.0"
ALIASES = {"v1": "1.0.0", "v1.0": "1.0.0", "v1.1": "1.1.0", "latest": "1.0.0"}


def resolve_version(name: str) -> ContractVersion:
    """Look up a version by exact number, by ``v`` prefixed number or by alias."""
    key = ALIASES.get(name, name.removeprefix("v"))
    if key not in VERSIONS:
        known = ", ".join([*VERSIONS, *ALIASES])
        raise KeyError(f"unknown contract version {name!r}; known: {known}")
    return VERSIONS[key]
