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
    wilson_interval,
)

SAMPLE_SETS = ("clean", "broken")
DEMO_SET = "broken"
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.\-]")
ALLOWED_SUFFIXES = (".ndjson", ".jsonl", ".csv", ".geojson", ".json")
CONFORMING_THRESHOLD = 0.9
RANKING_SEED = 20260422


def conformance_trend(result: Any) -> list[dict[str, Any]]:
    """Share of crash records passing every error and warning rule, per producer and local year."""
    out = []
    for feed in result.validated():
        if feed.feed_type != "crash_records":
            continue
        failing: set[int] = set()
        for o in result.outcomes:
            if (
                o.file == feed.file
                and o.status == "evaluated"
                and o.rule.severity != "info"
                and o.rule.scope != "file"
                and not o.findings.empty
            ):
                failing.update(int(r) for r in o.findings["_row"].dropna())
        frame = result.con.execute(
            f"SELECT _row, year(occurred_at__ts + INTERVAL 4 HOUR) AS y FROM {feed.table} "
            "WHERE occurred_at__ts IS NOT NULL"
        ).df()
        for year, group in frame.groupby("y"):
            total = len(group)
            passing = total - int(group["_row"].isin(failing).sum())
            iv = wilson_interval(passing, total)
            out.append(
                {
                    "producer_id": feed.producer_id,
                    "period": str(int(year)),
                    "passing": passing,
                    "total": total,
                    **iv.as_dict(),
                }
            )
    return sorted(out, key=lambda r: (str(r["producer_id"]), r["period"]))


def explain(row: dict[str, Any]) -> dict[str, Any]:
    """Plain language reasons for a segment's rank, as structured parts for translation."""
    if row["abstained"]:
        return {"kind": "abstained", "reasons": row["abstained"].split(";")}
    observed_per_year = row["observed"] / row["window_years"] if row["window_years"] else 0.0
    predicted = row["predicted_per_year"] or 0.0
    return {
        "kind": "ranked",
        "observed_per_year": observed_per_year,
        "predicted_per_year": predicted,
        "ratio": observed_per_year / predicted if predicted else None,
        "eb_weight": row["eb_weight"],
        "eb_per_year": row["eb_per_year"],
        "psi_per_year": row["psi_per_year"],
        "rank": row["rank"],
        "rank_low": row["rank_low"],
        "rank_high": row["rank_high"],
        "p_top_k": row["p_top_k"],
        "unresolved_pairs": row["unresolved_pairs"],
        "quality_factor": row["quality_factor"],
    }


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
    _datasets: dict[str, Any] = field(default_factory=dict)
    _lineage: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    _rankings: dict[str, Any] = field(default_factory=dict)

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

    def contract_diff(self, old: str, new: str) -> dict[str, Any]:
        from sikka.contract import diff_versions

        try:
            diff = diff_versions(resolve_version(old), resolve_version(new))
        except KeyError as exc:
            raise NotFoundError(str(exc.args[0])) from exc
        return diff.as_dict()

    def rules(self) -> list[dict[str, Any]]:
        from sikka.conformance import REGISTRY

        return [REGISTRY[k].as_dict() for k in sorted(REGISTRY)]

    def faults(self) -> dict[str, Any]:
        """The public fault catalogue shipped with the samples (no ground truth)."""
        import json

        path = self.paths.samples / "fault_catalogue.json"
        catalogue: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return catalogue

    def method(self) -> dict[str, Any]:
        """Method summary and preregistered evaluation results, read from results/*.json."""
        import json

        results: dict[str, Any] = {}
        for name in (
            "predictions",
            "e1_fault_detection",
            "e2_entity_resolution",
            "e3_blackspot_ranking",
            "e4_robustness",
            "e5_tasking",
            "performance",
        ):
            path = self.paths.results / f"{name}.json"
            if path.is_file():
                doc = json.loads(path.read_text(encoding="utf-8"))
                doc.pop("per_seed", None)
                results[name] = doc
        ranking = self.segments_ranking()["summary"]
        return {
            "notice": SYNTHETIC_NOTICE,
            "ranking": ranking,
            "results": results,
        }

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

    def network(self) -> dict[str, Any]:
        """The synthetic road network (clean registry samples) as one FeatureCollection."""
        import json

        features: list[dict[str, Any]] = []
        clean = self.paths.samples / "clean"
        for path in sorted(clean.glob("road_segments_*.geojson")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for feature in doc.get("features", []):
                props = feature.get("properties", {})
                features.append(
                    {
                        "type": "Feature",
                        "geometry": feature.get("geometry"),
                        "properties": {
                            "segment_id": props.get("segment_id"),
                            "road_name_en": props.get("road_name_en"),
                            "road_name_ar": props.get("road_name_ar"),
                            "road_class": props.get("road_class"),
                            "length_m": props.get("length_m"),
                        },
                    }
                )
        return {"type": "FeatureCollection", "synthetic": True, "features": features}

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

    # Harmonised data and lineage ------------------------------------------

    def dataset(self, label: str = DEMO_SET) -> Any:
        """The harmonised sample set (cached), built by the L4 pipeline."""
        from sikka.harmonise import harmonise

        if label not in SAMPLE_SETS:
            raise NotFoundError(f"unknown dataset {label!r}")
        if label not in self._datasets:
            folder = self.paths.samples / label
            sources = [Source.from_path(p) for p in sorted(folder.iterdir()) if p.is_file()]
            self._datasets[label] = harmonise(sources)
        return self._datasets[label]

    def _lineage_entries(self) -> dict[str, dict[str, Any]]:
        if DEMO_SET not in self._lineage:
            self._lineage[DEMO_SET] = self.dataset().lineage_index()
        return self._lineage[DEMO_SET]

    def lineage_index(self, query: str = "", limit: int = 0) -> dict[str, Any]:
        entries = self._lineage_entries()
        items = []
        needle = query.strip().upper()
        for cid, entry in sorted(entries.items()):
            sources = entry["lineage"]["sources"]
            record_ids = [s.get("record_id") for s in sources if s.get("record_id")]
            if needle and needle not in cid and not any(needle in r.upper() for r in record_ids):
                continue
            record = entry["record"]
            items.append(
                {
                    "canonical_id": cid,
                    "kind": entry["kind"],
                    "segment_id": record.get("segment_id"),
                    "status": entry["lineage"]["status"],
                    "sources": len(sources),
                    "record_ids": record_ids[:4],
                }
            )
            if limit and len(items) >= limit:
                break
        return {"dataset": DEMO_SET, "count": len(items), "items": items}

    def lineage(self, canonical_id: str) -> dict[str, Any]:
        entry: dict[str, Any] | None = self._lineage_entries().get(canonical_id)
        if entry is None:
            raise NotFoundError(f"no canonical record with id {canonical_id!r}")
        return entry

    def resolution_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = self.dataset().resolution_summary()
        return summary

    # Ranking -----------------------------------------------------------------

    def ranking_bundle(self, label: str = DEMO_SET) -> Any:
        from sikka.analytics import rank_dataset

        if label not in self._rankings:
            self._rankings[label] = rank_dataset(self.dataset(label), seed=RANKING_SEED)
        return self._rankings[label]

    def segments_ranking(self, label: str = DEMO_SET) -> dict[str, Any]:
        bundle = self.ranking_bundle(label)
        rows = bundle.segment_rows()
        return {
            "dataset": label,
            "notice": SYNTHETIC_NOTICE,
            "summary": bundle.summary(),
            "segments": rows,
        }

    def segment(self, segment_id: str, label: str = DEMO_SET) -> dict[str, Any]:
        rows = {r["segment_id"]: r for r in self.ranking_bundle(label).segment_rows()}
        if segment_id not in rows:
            raise NotFoundError(f"no segment with id {segment_id!r}")
        row: dict[str, Any] = rows[segment_id]
        clean = {r["segment_id"]: r for r in self.ranking_bundle("clean").segment_rows()}
        return row | {
            "dataset": label,
            "explanation": explain(row),
            "geometry": self._geometry(segment_id),
            "clean_comparison": clean.get(segment_id),
        }

    def _geometry(self, segment_id: str) -> dict[str, Any] | None:
        for feature in self.network()["features"]:
            if feature["properties"]["segment_id"] == segment_id:
                geometry: dict[str, Any] = feature["geometry"]
                return geometry
        return None

    # Tasking -----------------------------------------------------------------

    def _tasking(self) -> dict[str, Any]:
        from sikka.tasking import TaskingConfig, compare_strategies

        if "plans" not in self._rankings:
            rows = self.ranking_bundle().segment_rows()
            geometry = {sid: seg.coordinates for sid, seg in self.dataset().segments.items()}
            self._rankings["plans"] = compare_strategies(
                rows, geometry, TaskingConfig(), seed=RANKING_SEED
            )
        plans: dict[str, Any] = self._rankings["plans"]
        return plans

    def tasking_missions(self) -> dict[str, Any]:
        from sikka.tasking import DISCLAIMER, DroneProfile, TaskingConfig, to_plan, validate_plan

        plans = self._tasking()
        rows = {r["segment_id"]: r for r in self.ranking_bundle().segment_rows()}
        chosen = plans["value_of_information"]
        missions = []
        for m in chosen["missions"]:
            plan_errors = validate_plan(to_plan(m))
            missions.append(
                m.as_dict() | {"plan_valid": not plan_errors, "plan_errors": plan_errors}
            )
        voi = {
            sid: (r["p_top_k"] or 0.0) * (1 - (r["p_top_k"] or 0.0))
            for sid, r in rows.items()
            if r["p_top_k"] is not None
        }
        return {
            "dataset": DEMO_SET,
            "notice": SYNTHETIC_NOTICE,
            "disclaimer": DISCLAIMER,
            "profile": DroneProfile().as_dict(),
            "budget_missions": TaskingConfig().max_missions,
            "missions": missions,
            "refused": [m.as_dict() for m in chosen["refused"]],
            "value_of_information": [
                {"segment_id": sid, "voi": v, "length_km": rows[sid]["length_km"]}
                for sid, v in sorted(voi.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "comparison": {
                name: {
                    "segments": p["segments"],
                    "value": p["value"],
                    "flight_s": p["flight_s"],
                    "missions": len(p["missions"]),
                }
                for name, p in plans.items()
            },
        }

    def tasking_export(self, fmt: str) -> tuple[str, str]:
        """Return (content, media type) for a GeoJSON or KML export of the planned missions."""
        import json

        from sikka.tasking import to_geojson, to_kml

        missions = self._tasking()["value_of_information"]["missions"]
        if fmt == "geojson":
            return json.dumps(to_geojson(missions), indent=1), "application/geo+json"
        if fmt == "kml":
            return to_kml(missions), "application/vnd.google-earth.kml+xml"
        raise InputError("format must be geojson or kml")

    def tasking_plan(self, mission_id: str) -> dict[str, Any]:
        from sikka.tasking import to_plan

        for m in self._tasking()["value_of_information"]["missions"]:
            if m.mission_id == mission_id:
                plan: dict[str, Any] = to_plan(m)
                return plan
        raise NotFoundError(f"no mission with id {mission_id!r}")

    # Producer conformance across the demo feeds -----------------------------

    def producer_conformance(self) -> dict[str, Any]:
        if self._conformance is not None:
            return self._conformance
        folder = self.paths.samples / DEMO_SET
        sources = [Source.from_path(p) for p in sorted(folder.iterdir()) if p.is_file()]
        result = run_validation(sources)
        try:
            report = build_report(result)
            trend = conformance_trend(result)
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
            "trend": trend,
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
