"""Static snapshot of every GET response, for hosting the web app without a backend.

Files are written under ``web/public/snapshot`` with the API path as the file
path and ``.json`` appended, for example ``v1/contract/1.0.0.json``. Sample
validations are precomputed and indexed in ``v1/samples.json``.
"""

from __future__ import annotations

import json
from typing import Any

from sikka.api.service import Service
from sikka.conformance import render_html
from sikka.contract import VERSIONS
from sikka.core import round_floats, stable_json_dumps

SNAPSHOT_ROOT = "web/public/snapshot"


def lineage_bucket(canonical_id: str) -> str:
    """Static lineage is split into buckets: CC-XY for crashes, else the prefix."""
    return canonical_id[:5] if canonical_id.startswith("CC-") else canonical_id[:2]


def snapshot_files(service: Service) -> dict[str, str]:
    """Relative path to JSON text for every snapshot file."""
    docs: dict[str, Any] = {}
    docs["v1/health"] = service.health() | {"mode": "static"}
    docs["v1/contract"] = service.contract()
    for version in VERSIONS:
        docs[f"v1/contract/{version}"] = service.contract(version)
    for old in VERSIONS:
        for new in VERSIONS:
            if old != new:
                docs[f"v1/contract/diff/{old}/{new}"] = service.contract_diff(old, new)
    docs["v1/rules"] = service.rules()
    docs["v1/faults"] = service.faults()
    conformance = service.producer_conformance()
    docs["v1/producers/conformance"] = conformance
    docs[f"v1/reports/{conformance['report_id']}"] = service.report(conformance["report_id"])
    samples = []
    for sample in service.samples():
        report = service.validate_sample(sample["name"])
        samples.append(sample | {"report_id": report["report_id"]})
        docs[f"v1/reports/{report['report_id']}"] = report
    docs["v1/samples"] = samples
    docs["v1/network"] = service.network()
    docs["v1/lineage"] = service.lineage_index()
    docs["v1/method"] = service.method()
    docs["v1/tasking/missions"] = service.tasking_missions()
    for label in ("broken", "clean"):
        suffix = "" if label == "broken" else "-clean"
        ranking = service.segments_ranking(label)
        docs[f"v1/segments/ranking{suffix}"] = ranking
    for row in docs["v1/segments/ranking"]["segments"]:
        docs[f"v1/segments/{row['segment_id']}"] = service.segment(row["segment_id"])
    buckets: dict[str, dict[str, Any]] = {}
    for item in docs["v1/lineage"]["items"]:
        cid = item["canonical_id"]
        buckets.setdefault(lineage_bucket(cid), {})[cid] = service.lineage(cid)
    for key, bucket in buckets.items():
        docs[f"v1/lineage-buckets/{key}"] = bucket
    files = {
        f"{SNAPSHOT_ROOT}/{path}.json": stable_json_dumps(round_floats(doc)) + "\n"
        for path, doc in sorted(docs.items())
    }
    for path, doc in docs.items():
        if path.startswith("v1/reports/"):
            files[f"{SNAPSHOT_ROOT}/{path}.html"] = render_html(doc)
    for fmt in ("geojson", "kml"):
        content, _ = service.tasking_export(fmt)
        files[f"{SNAPSHOT_ROOT}/downloads/sikka-missions.{fmt}"] = content
    for mission in docs["v1/tasking/missions"]["missions"]:
        mid = mission["mission_id"]
        plan = json.dumps(service.tasking_plan(mid), indent=1)
        files[f"{SNAPSHOT_ROOT}/downloads/{mid}.plan"] = plan
    return files
