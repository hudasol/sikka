from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sikka.api import Service, create_app, safe_filename, snapshot_files
from sikka.conformance import BASE_HEADER, BASE_RECORDS
from sikka.contract.feedfile import render_ndjson
from sikka.core import InputError, Paths

ROOT = Paths().root
PROBLEM = "application/problem+json"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    store = tmp_path_factory.mktemp("reports")
    return TestClient(create_app(Service(store_dir=store, max_upload_bytes=200_000)))


def small_feed(n: int = 2) -> bytes:
    records = [dict(BASE_RECORDS["crash_records"]) | {"crash_id": f"PB-{i:07d}"} for i in range(n)]
    header = dict(BASE_HEADER) | {"record_count": n}
    return render_ndjson(header, records).encode("utf-8")


def assert_problem(response: Any, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith(PROBLEM)
    body: dict[str, Any] = response.json()
    assert set(body) == {"type", "title", "status", "detail", "instance"}
    assert body["status"] == status
    return body


def assert_no_paths(payload: Any) -> None:
    text = json.dumps(payload)
    assert str(ROOT) not in text
    assert str(ROOT).replace("\\", "/") not in text
    assert ":\\\\" not in text


def test_health(client: TestClient) -> None:
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "live"
    assert body["notice"].startswith("Synthetic data.")


def test_contract_endpoints(client: TestClient) -> None:
    body = client.get("/v1/contract").json()
    assert body["current"] == "1.0.0"
    assert [v["version"] for v in body["versions"]] == ["1.0.0", "1.1.0"]
    draft = client.get("/v1/contract/1.1.0").json()
    names = [f["name"] for f in draft["feeds"]["crash_records"]["fields"]]
    assert "work_zone" in names
    assert client.get("/v1/contract/v1").json()["version"] == "1.0.0"
    assert_problem(client.get("/v1/contract/9.9.9"), 404)


def test_network(client: TestClient) -> None:
    body = client.get("/v1/network").json()
    assert body["synthetic"] is True
    assert len(body["features"]) == 240
    assert body["features"][0]["geometry"]["type"] == "LineString"


def test_samples(client: TestClient) -> None:
    samples = client.get("/v1/samples").json()
    names = {s["name"] for s in samples}
    assert "broken/crash_records_producer_b.ndjson" in names
    assert_no_paths(samples)


def test_validate_sample_and_fetch_report(client: TestClient) -> None:
    response = client.post(
        "/v1/validate", data={"sample": "broken/crash_records_producer_d.ndjson"}
    )
    assert response.status_code == 201, response.text
    rid = response.json()["report_id"]
    report = client.get(f"/v1/reports/{rid}").json()
    assert report["report_id"] == rid
    assert report["files"][0]["file"] == "crash_records_producer_d.ndjson"
    assert_no_paths(report)
    html = client.get(f"/v1/reports/{rid}", params={"format": "html"})
    assert html.headers["content-type"].startswith("text/html")
    assert "Synthetic data." in html.text
    assert_problem(client.get(f"/v1/reports/{rid}", params={"format": "xml"}), 400)


def test_upload_is_idempotent(client: TestClient) -> None:
    files = {"file": ("mine.ndjson", small_feed(), "application/x-ndjson")}
    first = client.post("/v1/validate", files=files).json()["report_id"]
    second = client.post("/v1/validate", files=files).json()["report_id"]
    assert first == second
    other = {"file": ("mine.ndjson", small_feed(3), "application/x-ndjson")}
    assert client.post("/v1/validate", files=other).json()["report_id"] != first


def test_report_survives_a_restart(client: TestClient, tmp_path: Path) -> None:
    files = {"file": ("again.ndjson", small_feed(4), "application/octet-stream")}
    rid = client.post("/v1/validate", files=files).json()["report_id"]
    service: Service = client.app.state.service  # type: ignore[attr-defined]
    fresh = TestClient(create_app(Service(store_dir=service.store_dir)))
    assert fresh.get(f"/v1/reports/{rid}").json()["report_id"] == rid


def test_upload_errors(client: TestClient) -> None:
    assert_problem(client.post("/v1/validate", json={"sample": "x"}), 415)
    assert_problem(client.post("/v1/validate", data={"other": "x"}), 400)
    bad_name = {"file": ("notes.txt", b"hello", "text/plain")}
    assert_problem(client.post("/v1/validate", files=bad_name), 400)
    bad_type = {"file": ("feed.ndjson", b"{}", "image/png")}
    assert_problem(client.post("/v1/validate", files=bad_type), 415)
    empty = {"file": ("feed.ndjson", b"   ", "application/x-ndjson")}
    assert_problem(client.post("/v1/validate", files=empty), 400)
    big = {"file": ("feed.ndjson", b"{}\n" * 100_000, "application/x-ndjson")}
    assert_problem(client.post("/v1/validate", files=big), 413)
    assert_problem(client.post("/v1/validate", data={"sample": "../secrets.ndjson"}), 404)
    assert_problem(client.post("/v1/validate", data={"sample": "clean/nope.csv"}), 404)


def test_not_found_and_validation_errors(client: TestClient) -> None:
    assert_problem(client.get("/v1/reports/RPT-0000"), 404)
    assert_problem(client.get("/v1/nothing-here"), 404)


def test_unexpected_errors_are_problems(tmp_path: Path) -> None:
    class Broken(Service):
        def health(self) -> dict[str, Any]:
            raise RuntimeError("boom")

    c = TestClient(create_app(Broken(store_dir=tmp_path)), raise_server_exceptions=False)
    body = assert_problem(c.get("/v1/health"), 500)
    assert "boom" not in body["detail"]


def test_openapi_lists_every_endpoint(client: TestClient) -> None:
    spec = client.get("/v1/openapi.json").json()
    for path in (
        "/v1/health",
        "/v1/contract",
        "/v1/validate",
        "/v1/reports/{report_id}",
        "/v1/producers/conformance",
    ):
        assert path in spec["paths"]


def test_producer_conformance(client: TestClient) -> None:
    body = client.get("/v1/producers/conformance").json()
    head = body["headline"]
    assert head["producers"] == 4
    assert head["producers_conforming_low"] <= head["producers_conforming"]
    assert head["producers_conforming"] <= head["producers_conforming_high"]
    assert {s["producer_id"] for s in body["scores"]} == {
        "PRODUCER_A",
        "PRODUCER_B",
        "PRODUCER_C",
        "PRODUCER_D",
    }
    assert_no_paths(body)


def test_lineage(client: TestClient) -> None:
    index = client.get("/v1/lineage", params={"limit": 500}).json()
    assert index["dataset"] == "broken"
    assert index["count"] == len(index["items"]) <= 500
    crash_id = next(i["canonical_id"] for i in index["items"] if i["kind"] == "crash")
    entry = client.get(f"/v1/lineage/{crash_id}").json()
    assert entry["canonical_id"] == crash_id
    assert entry["lineage"]["sources"]
    by_record = client.get("/v1/lineage", params={"q": "PB-0000007"}).json()
    assert any("PB-0000007" in i["record_ids"] for i in by_record["items"])
    exposure = client.get("/v1/lineage/EX-SEG-DUN-001")
    assert exposure.status_code in {200, 404}
    assert client.get("/v1/lineage/SG-SEG-DUN-001").json()["kind"] == "segment"
    assert_problem(client.get("/v1/lineage/CC-NOPE"), 404)
    assert_problem(client.get("/v1/lineage", params={"limit": 0}), 400)
    text = json.dumps(client.get("/v1/lineage", params={"limit": 500}).json())
    assert "Synthetic Person" not in text
    assert_no_paths(entry)


def test_safe_filename() -> None:
    assert safe_filename("C:\\Users\\x\\my feed.csv") == "my_feed.csv"
    assert safe_filename("../../etc/a.ndjson") == "a.ndjson"
    with pytest.raises(InputError):
        safe_filename("a.exe")


@pytest.mark.slow
def test_static_snapshot_is_fresh() -> None:
    files = snapshot_files(Service(mode="static"))
    stale = [rel for rel, text in files.items() if (ROOT / rel).read_bytes() != text.encode()]
    assert not stale, f"run `sikka snapshot`; stale: {stale}"
