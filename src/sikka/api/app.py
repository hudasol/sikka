"""FastAPI application. Versioned under /v1, errors as application/problem+json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from sikka import __version__
from sikka.api.service import Service
from sikka.conformance import render_html
from sikka.core import (
    InputError,
    PayloadTooLargeError,
    SikkaError,
    UnsupportedMediaTypeError,
    get_logger,
)

PROBLEM = "application/problem+json"
UPLOAD_TYPES = {
    "",
    "application/octet-stream",
    "application/x-ndjson",
    "application/jsonl",
    "application/json",
    "application/geo+json",
    "text/csv",
    "text/plain",
}
log = get_logger("api")


def problem(status: int, title: str, detail: str, instance: str) -> JSONResponse:
    return JSONResponse(
        {
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": instance,
        },
        status_code=status,
        media_type=PROBLEM,
    )


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or Service(store_dir=Path("build") / "api-reports")
    app = FastAPI(
        title="Sikka API",
        version=__version__,
        description=(
            "Data contract checks and blackspot ranking for road feeds. Synthetic data only. "
            "A proposal seed, not an official service."
        ),
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    app.state.service = svc
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(SikkaError)
    async def _sikka_error(request: Request, exc: SikkaError) -> JSONResponse:
        return problem(exc.status, exc.title, str(exc), request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = "Not found" if exc.status_code == 404 else "Request error"
        return problem(exc.status_code, title, str(exc.detail), request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        return problem(
            422, "Invalid request", f"check these parameters: {fields}", request.url.path
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unexpected error on %s: %s", request.url.path, type(exc).__name__)
        return problem(
            500, "Internal error", "the request could not be completed", request.url.path
        )

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return svc.health()

    @app.get("/v1/contract")
    def contract() -> dict[str, Any]:
        return svc.contract()

    @app.get("/v1/contract/{version}")
    def contract_version(version: str) -> dict[str, Any]:
        return svc.contract(version)

    @app.get("/v1/samples")
    def samples() -> list[dict[str, Any]]:
        return svc.samples()

    @app.get("/v1/network")
    def network() -> dict[str, Any]:
        return svc.network()

    @app.post("/v1/validate", status_code=201)
    async def validate(request: Request) -> dict[str, Any]:
        ctype = request.headers.get("content-type", "")
        if not ctype.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
            raise UnsupportedMediaTypeError(
                "send the feed as multipart/form-data, or a sample name as a form field"
            )
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > svc.max_upload_bytes + 65536:
            raise PayloadTooLargeError(
                f"upload is larger than {svc.max_upload_bytes // (1024 * 1024)} MB"
            )
        form = await request.form()
        sample = form.get("sample")
        upload = form.get("file")
        if isinstance(sample, str) and sample:
            report = svc.validate_sample(sample)
        elif upload is not None and not isinstance(upload, str):
            assert isinstance(upload, UploadFile)
            if (upload.content_type or "").split(";")[0].strip() not in UPLOAD_TYPES:
                raise UnsupportedMediaTypeError(
                    f"content type {upload.content_type!r} is not accepted"
                )
            data = await upload.read(svc.max_upload_bytes + 1)
            report = svc.validate_bytes(upload.filename or "upload", data)
        else:
            raise InputError("provide a file field or a sample field")
        return {"report_id": report["report_id"], "notice": report["notice"]}

    @app.get("/v1/reports/{report_id}")
    def report(report_id: str, format: str = "json") -> Any:
        data = svc.report(report_id)
        if format == "html":
            return HTMLResponse(render_html(data))
        if format != "json":
            raise InputError("format must be json or html")
        return data

    @app.get("/v1/lineage")
    def lineage_index(q: str = "", limit: int = 50) -> dict[str, Any]:
        if not 0 < limit <= 500:
            raise InputError("limit must be between 1 and 500")
        return svc.lineage_index(q, limit)

    @app.get("/v1/lineage/{canonical_id}")
    def lineage(canonical_id: str) -> dict[str, Any]:
        return svc.lineage(canonical_id)

    @app.get("/v1/segments/ranking")
    def segments_ranking(dataset: str = "broken") -> dict[str, Any]:
        return svc.segments_ranking(dataset)

    @app.get("/v1/segments/{segment_id}")
    def segment(segment_id: str, dataset: str = "broken") -> dict[str, Any]:
        return svc.segment(segment_id, dataset)

    @app.get("/v1/producers/conformance")
    def producers_conformance() -> dict[str, Any]:
        return svc.producer_conformance()

    return app
