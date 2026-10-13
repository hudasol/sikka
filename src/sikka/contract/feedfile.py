"""Feed file formats. Pure rendering; reading lives in the ingestion layer.

Three encodings are supported, each starting with the provenance header:

* NDJSON: the first line is ``{"sikka_header": {...}}``; each further line is one record.
* CSV: the first line is ``# sikka_header: {...}`` (JSON); the second line holds the
  column names; nested objects are flattened with dotted names
  (``class_counts.car``); lists are joined with ``;``; nested geometry is a JSON
  string; an empty cell means the field is absent.
* GeoJSON: a ``FeatureCollection`` with a ``sikka_header`` member. Each feature's
  properties are the record; a LineString geometry becomes the ``geometry`` field.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from sikka.contract.conventions import HEADER_KEY

FeedFormat = Literal["ndjson", "csv", "geojson"]
FORMAT_SUFFIX: dict[str, str] = {"ndjson": ".ndjson", "csv": ".csv", "geojson": ".geojson"}
CSV_HEADER_PREFIX = f"# {HEADER_KEY}: "
LIST_SEPARATOR = ";"


def public_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Drop private bookkeeping keys (those starting with ``__``)."""
    return {k: v for k, v in record.items() if not k.startswith("__")}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render_ndjson(header: Mapping[str, Any], records: Iterable[Mapping[str, Any]]) -> str:
    lines = [_dumps({HEADER_KEY: dict(header)})]
    lines.extend(_dumps(public_fields(r)) for r in records)
    return "\n".join(lines) + "\n"


def flatten_for_csv(record: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in public_fields(record).items():
        if key == "geometry" and isinstance(value, dict):
            out[key] = _dumps(value)
        elif isinstance(value, dict):
            for sub, sub_value in value.items():
                out[f"{key}.{sub}"] = "" if sub_value is None else str(sub_value)
        elif isinstance(value, list):
            out[key] = LIST_SEPARATOR.join(str(v) for v in value)
        elif isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif value is None:
            out[key] = ""
        else:
            out[key] = str(value)
    return out


def render_csv(
    header: Mapping[str, Any],
    records: Iterable[Mapping[str, Any]],
    columns: list[str] | None = None,
) -> str:
    """CSV with the header comment line. Columns default to first seen order."""
    flat = [flatten_for_csv(r) for r in records]
    if columns is None:
        columns = []
        seen: set[str] = set()
        for row in flat:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    buf = io.StringIO()
    buf.write(CSV_HEADER_PREFIX + _dumps(dict(header)) + "\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in flat:
        writer.writerow([row.get(c, "") for c in columns])
    return buf.getvalue()


def render_geojson(header: Mapping[str, Any], records: Iterable[Mapping[str, Any]]) -> str:
    features = []
    for record in records:
        props = public_fields(record)
        geometry = props.pop("geometry", None)
        features.append({"type": "Feature", "geometry": geometry, "properties": props})
    doc = {"type": "FeatureCollection", HEADER_KEY: dict(header), "features": features}
    return json.dumps(doc, ensure_ascii=False, indent=None, separators=(",", ":")) + "\n"


def render_feed(
    fmt: FeedFormat, header: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> str:
    if fmt == "ndjson":
        return render_ndjson(header, records)
    if fmt == "csv":
        return render_csv(header, records)
    return render_geojson(header, records)
