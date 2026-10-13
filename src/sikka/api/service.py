"""Service functions behind the HTTP API and the static snapshot.

Every function returns plain JSON compatible data. The HTTP layer and the
snapshot builder call the same functions, so the static demo shows exactly what
the live API would return.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sikka import __version__
from sikka.conformance import SYNTHETIC_NOTICE, Source, build_report, run_validation
from sikka.contract import CURRENT_VERSION, VERSIONS, contract_bundle, resolve_version
from sikka.core import (
    MAX_UPLOAD_BYTES,
    InputError,
    NotFoundError,
    Paths,
    stable_json_dumps,
)

SAMPLE_SETS = ("clean", "broken")
DEMO_SET = "broken"
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.\-]")
ALLOWED_SUFFIXES = (".ndjson", ".jsonl", ".csv", ".geojson", ".json")
CONFORMING_THRESHOLD = 0.9


def safe_filename(name: str) -> str:
    """Keep only the base name and a conservative character set."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = SAFE_NAME.sub("_", base)[:120] or "upload"
    if not cleaned.lower().endswith(ALLOWED_SUFFIXES):
        raise InputError("only .ndjson, .jsonl, .csv, .geojson or .json files are accepted")
    return cleaned


@dataclass
class Service:
    """Holds paths and caches; safe to share between requests."""

    paths: Paths = field(default_factory=Paths)
    store_dir: Path | None = None
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    mode: str = "live"
    _reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    _conformance: dict[str, Any] | None = None

    # Basic endpoints --------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "mode": self.mode,
            "contract_version": CURRENT_VERSION,
            "notice": SYNTHETIC_NOTICE,
        }

    def contract(self, version: str | None = None) -> dict[str, Any]:
        if version is None:
            return {
                "current": CURRENT_VERSION,
                "versions": [
                    {"version": v.version, "status": v.status, "summary": v.summary}
                    for v in VERSIONS.values()
                ],
                "bundle": contract_bundle(VERSIONS[CURRENT_VERSION]),
            }
        try:
            return contract_bundle(resolve_version(version))
        except KeyError as exc:
            raise NotFoundError(f"unknown contract version {version!r}") from exc

    # Samples ----------------------------------------------------------------

    def sample_path(self, name: str) -> Path:
        parts = name.split("/")
        if len(parts) != 2 or parts[0] not in SAMPLE_SETS or not parts[1]:
            raise NotFoundError(f"unknown sample {name!r}")
        path = self.paths.samples / parts[0] / parts[1]
        if not path.is_file() or path.parent.parent != self.paths.samples:
            raise NotFoundError(f"unknown sample {name!r}")
        return path

    def samples(self) -> list[dict[str, Any]]:
        out = []
        for label in SAMPLE_SETS:
            folder = self.paths.samples / label
            for path in sorted(folder.iterdir()) if folder.is_dir() else []:
                if path.is_file():
                    out.append(
                        {
                            "name": f"{label}/{path.name}",
                            "set": label,
                            "file": path.name,
                            "bytes": path.stat().st_size,
                        }
                    )
        return out

    def _references(self, exclude: set[str]) -> list[Source]:
        clean = self.paths.samples / "clean"
        return [
            Source.from_path(p)
            for p in sorted(clean.iterdir())
            if p.is_file() and p.name not in exclude
        ]

    # Validation -------------------------------------------------------------

    def _store(self, report: dict[str, Any]) -> dict[str, Any]:
        rid = report["report_id"]
        self._reports[rid] = report
        if self.store_dir is not None:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            (self.store_dir / f"{rid}.json").write_text(
                stable_json_dumps(report) + "\n", encoding="utf-8"
            )
        return report

    def validate_bytes(self, name: str, data: bytes) -> dict[str, Any]:
        if len(data) > self.max_upload_bytes:
            from sikka.core import PayloadTooLargeError

            raise PayloadTooLargeError(
                f"upload is larger than {self.max_upload_bytes // (1024 * 1024)} MB"
            )
        if not data.strip():
            raise InputError("the uploaded file is empty")
        filename = safe_filename(name)
        result = run_validation([Source.from_bytes(filename, data)], self._references({filename}))
        try:
            report = build_report(result)
        finally:
            result.close()
        return self._store(report)

    def validate_sample(self, name: str) -> dict[str, Any]:
        path = self.sample_path(name)
        return self.validate_bytes(path.name, path.read_bytes())

    def report(self, report_id: str) -> dict[str, Any]:
        if report_id in self._reports:
            return self._reports[report_id]
        if self.store_dir is not None and re.fullmatch(r"RPT-[A-F0-9]{20}", report_id):
            path = self.store_dir / f"{report_id}.json"
            if path.is_file():
                import json

                report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                self._reports[report_id] = report
                return report
        raise NotFoundError(f"no report with id {report_id!r}")

    # Producer conformance across the demo feeds -----------------------------

    def producer_conformance(self) -> dict[str, Any]:
        if self._conformance is not None:
            return self._conformance
        folder = self.paths.samples / DEMO_SET
        sources = [Source.from_path(p) for p in sorted(folder.iterdir()) if p.is_file()]
        result = run_validation(sources)
        try:
            report = build_report(result)
        finally:
            result.close()
        self._store(report)
        overall = [s for s in report["scores"] if s["family"] == "ALL"]
        conforming_low = sum(1 for s in overall if s["low"] >= CONFORMING_THRESHOLD)
        conforming_high = sum(1 for s in overall if s["high"] >= CONFORMING_THRESHOLD)
        conforming = sum(1 for s in overall if s["estimate"] >= CONFORMING_THRESHOLD)
        flagged = sum(r["records"] for r in report["rules"] if r["severity"] != "info")
        total = sum(f["rows"] for f in report["files"])
        self._conformance = {
            "dataset": DEMO_SET,
            "dataset_note": "Synthetic sample feeds as received, with every catalogued fault "
            "injected at 3 percent.",
            "report_id": report["report_id"],
            "scores": report["scores"],
            "file_checks": report["file_checks"],
            "families": report["families"],
            "score_definition": report["score_definition"],
            "headline": {
                "producers": len(overall),
                "conforming_threshold": CONFORMING_THRESHOLD,
                "producers_conforming": conforming,
                "producers_conforming_low": conforming_low,
                "producers_conforming_high": conforming_high,
                "rules_failing": report["rules_failing"],
                "rules_total": len({r["rule_id"] for r in report["rules"]}),
                "records_total": total,
                "flagged_record_findings": flagged,
            },
        }
        return self._conformance
