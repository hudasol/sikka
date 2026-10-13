"""Streaming parsers for NDJSON, CSV and GeoJSON feeds.

Every parser yields records as JSON text, one per row, so the staging step
never needs the whole file in memory (GeoJSON registries are the exception:
they are small and are read in one piece). Values keep their JSON types; CSV
cells are typed from the contract only when they parse cleanly with ASCII
digits, so a value such as an Arabic Indic digit string stays a string and the
type rule can see it.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sikka.contract import CURRENT_VERSION, HEADER_KEY, VERSIONS, field_specs, version_schemas
from sikka.contract.feedfile import CSV_HEADER_PREFIX
from sikka.core import InputError

_NUM = re.compile(r"^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$")
FEED_KEYS = {
    "road_segments": "segment_id",
    "crash_records": "crash_id",
    "traffic_counts": "station_id",
}


def contract_types(feed_type: str) -> dict[str, str]:
    """Field name (dotted for nested) to the field dictionary type label."""
    schema = version_schemas(VERSIONS[CURRENT_VERSION])[feed_type]
    return {s.name: s.type for s in field_specs(schema, feed_type)}


_TYPES = {ft: contract_types(ft) for ft in FEED_KEYS}


def infer_feed_type(keys: set[str]) -> str | None:
    """Guess the feed type from the identifier field a record carries."""
    for feed_type, key in FEED_KEYS.items():
        if key in keys:
            return feed_type
    return None


def detect_format(name: str) -> str:
    lower = name.lower()
    for suffix, fmt in ((".ndjson", "ndjson"), (".jsonl", "ndjson"), (".csv", "csv")):
        if lower.endswith(suffix):
            return fmt
    if lower.endswith((".geojson", ".json")):
        return "geojson"
    raise InputError(f"unsupported file type: {name}; use .ndjson, .csv or .geojson")


@dataclass
class ParsedFeed:
    """A feed opened for streaming. ``rows`` yields JSON text, one record per row."""

    name: str
    fmt: str
    header: dict[str, Any] | None
    header_error: str | None
    feed_type: str | None
    rows: Iterator[str]
    columns: list[str] = field(default_factory=list)


_ASCII_NUMBER = frozenset("0123456789.-+eE")


def _coerce(value: str, kind: str) -> Any:
    if value == "":
        return None
    if kind == "integer":
        body = value[1:] if value[:1] == "-" else value
        return int(value) if body.isascii() and body.isdigit() else value
    if kind == "number":
        if not _ASCII_NUMBER.issuperset(value) or not _NUM.match(value):
            return value
        return float(value) if any(c in value for c in ".eE") else int(value)
    if kind == "boolean" and value in {"true", "false"}:
        return value == "true"
    if kind in {"list of enum", "list of positions", "object"} and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def csv_row_to_record(row: dict[str, str], types: dict[str, str]) -> dict[str, Any]:
    """Convert one CSV row (column name to cell text) into a record."""
    plan = _plan(list(row), types)
    return _convert([row[c] for c in row], plan)


Plan = list[tuple[str, str | None, str]]


def _plan(columns: list[str], types: dict[str, str]) -> Plan:
    out: Plan = []
    for column in columns:
        if "." in column:
            parent, child = column.split(".", 1)
            out.append((child, parent, types.get(column, "string")))
        else:
            out.append((column, None, types.get(column, "string")))
    return out


def _convert(cells: list[str], plan: Plan) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for (name, parent, kind), cell in zip(plan, cells, strict=False):
        if cell == "" or cell is None:
            continue
        value = _coerce(cell, kind)
        if parent is None:
            record[name] = value
        else:
            nested = record.setdefault(parent, {})
            if isinstance(nested, dict):
                nested[name] = value
    return record


def _parse_header(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None, "header line is not valid JSON"
    if not isinstance(doc, dict):
        return None, "header is not an object"
    return doc, None


def _ndjson(name: str, stream: io.TextIOBase) -> ParsedFeed:
    first = stream.readline().rstrip("\r\n")
    header: dict[str, Any] | None = None
    error: str | None = None
    pending: list[str] = []
    try:
        doc = json.loads(first) if first else None
    except json.JSONDecodeError:
        doc = None
    if isinstance(doc, dict) and HEADER_KEY in doc:
        header = doc[HEADER_KEY] if isinstance(doc[HEADER_KEY], dict) else None
        error = None if header is not None else "header is not an object"
    else:
        error = "missing provenance header"
        if first:
            pending.append(first)
    feed_type = header.get("feed_type") if header else None
    if feed_type not in FEED_KEYS:
        probe = pending[0] if pending else None
        if probe is None:
            pos = stream.tell()
            probe = stream.readline()
            stream.seek(pos)
        try:
            keys = set(json.loads(probe)) if probe else set()
        except (json.JSONDecodeError, TypeError):
            keys = set()
        feed_type = infer_feed_type(keys)

    def rows() -> Iterator[str]:
        yield from pending
        for line in stream:
            line = line.rstrip("\r\n")
            if line.strip():
                yield line

    return ParsedFeed(name, "ndjson", header, error, feed_type, rows())


def _csv(name: str, stream: io.TextIOBase) -> ParsedFeed:
    first = stream.readline().rstrip("\r\n")
    header: dict[str, Any] | None = None
    error: str | None = None
    if first.startswith(CSV_HEADER_PREFIX):
        header, error = _parse_header(first[len(CSV_HEADER_PREFIX) :])
        columns_line = stream.readline()
    else:
        error = "missing provenance header"
        columns_line = first + "\n"
    columns = next(csv.reader([columns_line]), [])
    feed_type = header.get("feed_type") if header else None
    if feed_type not in FEED_KEYS:
        feed_type = infer_feed_type(set(columns))
    plan = _plan(columns, _TYPES.get(str(feed_type), {}))
    reader = csv.reader(stream)
    dumps = json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).encode

    def rows() -> Iterator[str]:
        for cells in reader:
            if cells:
                yield dumps(_convert(cells, plan))

    return ParsedFeed(name, "csv", header, error, feed_type, rows(), columns)


def _geojson(name: str, stream: io.TextIOBase) -> ParsedFeed:
    try:
        doc = json.load(stream)
    except json.JSONDecodeError as exc:
        raise InputError(f"{name} is not valid JSON") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("features"), list):
        raise InputError(f"{name} is not a GeoJSON FeatureCollection")
    raw_header = doc.get(HEADER_KEY)
    header = raw_header if isinstance(raw_header, dict) else None
    error = None if header is not None else "missing provenance header"
    features = [f for f in doc["features"] if isinstance(f, dict)]
    feed_type = header.get("feed_type") if header else None
    if feed_type not in FEED_KEYS:
        probe = features[0].get("properties", {}) if features else {}
        feed_type = infer_feed_type(set(probe) if isinstance(probe, dict) else set())

    def rows() -> Iterator[str]:
        for feature in features:
            props = feature.get("properties")
            record = dict(props) if isinstance(props, dict) else {}
            geometry = feature.get("geometry")
            if isinstance(geometry, dict):
                if geometry.get("type") == "Point" and feed_type == "crash_records":
                    coords = geometry.get("coordinates") or [None, None]
                    record.setdefault("lon", coords[0])
                    record.setdefault("lat", coords[1])
                else:
                    record["geometry"] = geometry
            yield json.dumps(record, ensure_ascii=False)

    return ParsedFeed(name, "geojson", header, error, feed_type, rows())


def open_text(name: str, stream: io.TextIOBase) -> ParsedFeed:
    """Open an already opened text stream. The caller keeps the stream open while reading."""
    fmt = detect_format(name)
    if fmt == "ndjson":
        return _ndjson(name, stream)
    if fmt == "csv":
        return _csv(name, stream)
    return _geojson(name, stream)


def open_feed(path: Path) -> tuple[ParsedFeed, io.TextIOBase]:
    """Open a feed file. Close the returned stream when done."""
    stream = path.open("r", encoding="utf-8-sig", newline="")
    try:
        return open_text(path.name, stream), stream
    except Exception:
        stream.close()
        raise
