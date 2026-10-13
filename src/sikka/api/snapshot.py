"""Static snapshot of every GET response, for hosting the web app without a backend.

Files are written under ``web/public/snapshot`` with the API path as the file
path and ``.json`` appended, for example ``v1/contract/1.0.0.json``. Sample
validations are precomputed and indexed in ``v1/samples.json``.
"""

from __future__ import annotations

from typing import Any

from sikka.api.service import Service
from sikka.contract import VERSIONS
from sikka.core import round_floats, stable_json_dumps

SNAPSHOT_ROOT = "web/public/snapshot"


def snapshot_files(service: Service) -> dict[str, str]:
    """Relative path to JSON text for every snapshot file."""
    docs: dict[str, Any] = {}
    docs["v1/health"] = service.health() | {"mode": "static"}
    docs["v1/contract"] = service.contract()
    for version in VERSIONS:
        docs[f"v1/contract/{version}"] = service.contract(version)
    conformance = service.producer_conformance()
    docs["v1/producers/conformance"] = conformance
    docs[f"v1/reports/{conformance['report_id']}"] = service.report(conformance["report_id"])
    samples = []
    for sample in service.samples():
        report = service.validate_sample(sample["name"])
        samples.append(sample | {"report_id": report["report_id"]})
        docs[f"v1/reports/{report['report_id']}"] = report
    docs["v1/samples"] = samples
    return {
        f"{SNAPSHOT_ROOT}/{path}.json": stable_json_dumps(round_floats(doc)) + "\n"
        for path, doc in sorted(docs.items())
    }
