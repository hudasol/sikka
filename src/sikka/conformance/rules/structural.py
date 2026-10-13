"""S family: structure of the file and of each record."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import ValidationError

from sikka.conformance.context import RuleContext
from sikka.conformance.fields import ID_FIELDS, specs, top_level
from sikka.conformance.registry import Example, Rule, findings, register
from sikka.contract import FEED_TYPES, VERSIONS, ProvenanceHeader
from sikka.core import ID_PATTERN

ALL = ("road_segments", "crash_records", "traffic_counts")
JSON_TYPES = {
    "identifier": ("VARCHAR",),
    "string": ("VARCHAR",),
    "timestamp": ("VARCHAR",),
    "enum": ("VARCHAR",),
    "constant": ("VARCHAR",),
    "integer": ("UBIGINT", "BIGINT"),
    "number": ("UBIGINT", "BIGINT", "DOUBLE"),
    "boolean": ("BOOLEAN",),
    "list of enum": ("ARRAY",),
    "list of positions": ("ARRAY",),
    "object": ("OBJECT",),
}


def q(name: str) -> str:
    return '"' + name + '"'


def sql_list(values: list[str] | tuple[str, ...]) -> str:
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


def union(ctx: RuleContext, selects: list[str]) -> pd.DataFrame:
    if not selects:
        return findings()
    frame = ctx.sql(" UNION ALL ".join(selects))
    if frame.empty:
        return findings()
    frame["_row"] = frame["_row"].astype("Int64")
    return frame[["_row", "series", "field", "detail"]]


def file_finding(detail: str, field: str | None = None) -> pd.DataFrame:
    return findings([{"_row": None, "series": None, "field": field, "detail": detail}])


# SK-S001 -------------------------------------------------------------------------


def s001(ctx: RuleContext) -> pd.DataFrame:
    if ctx.feed.header is None:
        return file_finding(ctx.feed.header_error or "missing provenance header")
    try:
        ProvenanceHeader.model_validate(ctx.feed.header)
    except ValidationError as exc:
        rows: list[dict[str, Any]] = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or None
            rows.append({"_row": None, "series": None, "field": loc, "detail": err["msg"]})
        return findings(rows)
    return findings()


register(
    Rule(
        "SK-S001",
        "S",
        "Provenance header present and valid",
        "error",
        "The file starts with a provenance header that has every required key with a valid value.",
        "Without the header nobody can tell who produced the file, for which period, under "
        "which licence, or whether it is synthetic.",
        "Add the sikka_header line (NDJSON, CSV) or member (GeoJSON) as described in the contract.",
        ALL,
        ("header",),
        "file",
        s001,
        Example("crash_records", {}, {}, header={"licence": ""}),
    )
)


def s002(ctx: RuleContext) -> pd.DataFrame:
    header = ctx.feed.header or {}
    declared = header.get("record_count")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared != ctx.feed.rows:
        return file_finding(
            f"header declares {declared} records, file has {ctx.feed.rows}", "record_count"
        )
    return findings()


register(
    Rule(
        "SK-S002",
        "S",
        "Declared record count matches",
        "error",
        "The header record_count equals the number of records in the file.",
        "A mismatch means the file was truncated, appended to, or the header was copied from "
        "another file.",
        "Recompute record_count when the file is written, after all filtering.",
        ALL,
        ("header.record_count",),
        "file",
        s002,
        Example("crash_records", {}, {}, header={"record_count": 99}),
    )
)


def s003(ctx: RuleContext) -> pd.DataFrame:
    header = ctx.feed.header or {}
    if header.get("synthetic") is not True:
        return file_finding(
            f"synthetic is {header.get('synthetic')!r}; every feed in this repository must be "
            "synthetic",
            "synthetic",
        )
    return findings()


register(
    Rule(
        "SK-S003",
        "S",
        "Synthetic flag set in a synthetic repository",
        "error",
        "The header synthetic flag is true.",
        "This repository only handles synthetic data. A false flag means real data may have "
        "been mixed in, or the flag is wrong; either way the file must not be used here.",
        "Set synthetic to true, or remove the file if it holds real records.",
        ALL,
        ("header.synthetic",),
        "file",
        s003,
        Example("crash_records", {}, {}, header={"synthetic": False}),
    )
)


def s004(ctx: RuleContext) -> pd.DataFrame:
    header = ctx.feed.header or {}
    out: list[dict[str, Any]] = []
    version = header.get("contract_version")
    if version not in VERSIONS:
        out.append(
            {
                "_row": None,
                "series": None,
                "field": "contract_version",
                "detail": f"unsupported contract version {version!r}",
            }
        )
    declared = header.get("feed_type")
    if declared not in FEED_TYPES:
        out.append(
            {
                "_row": None,
                "series": None,
                "field": "feed_type",
                "detail": f"unknown feed type {declared!r}",
            }
        )
    elif ctx.feed.feed_type and declared != ctx.feed.feed_type:
        out.append(
            {
                "_row": None,
                "series": None,
                "field": "feed_type",
                "detail": f"header says {declared}, records look like {ctx.feed.feed_type}",
            }
        )
    return findings(out)


register(
    Rule(
        "SK-S004",
        "S",
        "Contract version and feed type supported",
        "error",
        "The header names a known contract version and one of the three feed types.",
        "Rules are defined per version and feed type; an unknown pair cannot be checked.",
        "Use contract_version 1.0.0 and feed_type road_segments, crash_records or traffic_counts.",
        ALL,
        ("header.contract_version", "header.feed_type"),
        "file",
        s004,
        Example("crash_records", {}, {}, header={"contract_version": "0.9.0"}),
    )
)


def s005(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name, spec in specs(ft).items():
        if not spec.required:
            continue
        if "." in name:
            parent = name.split(".")[0]
            cond = f"{q(parent + '__t')} = 'OBJECT' AND {q(name + '__t')} IS NULL"
        else:
            cond = f"{q(name + '__t')} IS NULL"
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, 'required field is missing' AS "
            f"detail FROM {ctx.table} WHERE {cond}"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-S005",
        "S",
        "Required fields present",
        "error",
        "Every required field of the feed is present in every record.",
        "Missing required fields usually mean a renamed column or a broken export.",
        "Check the export mapping against the field dictionary, especially after system changes.",
        ALL,
        ("*",),
        "record",
        s005,
        Example("crash_records", {"occurred_at": None}, {}),
    )
)


def s006(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    allowed = sql_list(list(top_level(ft)))
    selects = [
        f"SELECT _row, NULL AS series, k AS field, 'field is not defined in the contract' AS "
        f"detail FROM (SELECT _row, unnest(_keys) AS k FROM {ctx.table}) WHERE k NOT IN {allowed}"
    ]
    for parent in ("class_counts", "geometry"):
        children = [n.split(".", 1)[1] for n in specs(ft) if n.startswith(parent + ".")]
        if not children:
            continue
        selects.append(
            f"SELECT _row, NULL AS series, '{parent}.' || k AS field, "
            f"'field is not defined in the contract' AS detail FROM (SELECT _row, "
            f"unnest(json_keys(_raw, '$.{parent}')) AS k FROM {ctx.table} "
            f"WHERE {q(parent + '__t')} = 'OBJECT') WHERE k NOT IN {sql_list(children)}"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-S006",
        "S",
        "No unknown fields",
        "warning",
        "Records only carry fields defined by the contract.",
        "Unknown fields are schema drift; they can hide renamed fields or personal data.",
        "Drop fields that are not in the contract, or propose a contract change.",
        ALL,
        ("*",),
        "record",
        s006,
        Example("crash_records", {"source_system": "LEGACY-7"}, {}),
    )
)


def s007(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = [
        f"SELECT _row, NULL AS series, NULL AS field, 'record is not valid JSON' AS detail "
        f"FROM {ctx.table}_invalid"
    ]
    for name, spec in specs(ft).items():
        expected = JSON_TYPES.get(spec.type)
        if expected is None:
            continue
        t = q(name + "__t")
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, CASE WHEN {t} = 'NULL' THEN "
            f"'null is not allowed; leave the field out instead' ELSE 'expected {spec.type}, "
            f"found ' || lower({t}) END AS detail FROM {ctx.table} WHERE {t} IS NOT NULL AND "
            f"{t} NOT IN {sql_list(expected)}"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-S007",
        "S",
        "Field types match the contract",
        "error",
        "Each field has the JSON type the contract defines; explicit null is not allowed.",
        "Numbers sent as text, epoch numbers in timestamp fields and nulls break downstream "
        "parsing silently.",
        "Emit numbers as JSON numbers with ASCII digits, timestamps as ISO 8601 strings, and "
        "omit missing fields.",
        ALL,
        ("*",),
        "record",
        s007,
        Example("crash_records", {"vehicles_involved": "two"}, {}),
    )
)


def s008(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name, spec in specs(ft).items():
        if not spec.enum:
            continue
        t, allowed = q(name + "__t"), sql_list(spec.enum)
        if spec.type == "enum":
            selects.append(
                f"SELECT _row, NULL AS series, '{name}' AS field, 'value ' || coalesce({q(name)}, "
                f"'?') || ' is not one of the allowed values' AS detail FROM {ctx.table} WHERE "
                f"{t} IS NOT NULL AND {t} <> 'NULL' AND ({t} <> 'VARCHAR' OR {q(name)} NOT IN "
                f"{allowed})"
            )
        else:
            selects.append(
                f"SELECT _row, NULL AS series, '{name}' AS field, 'list holds values outside the "
                f"allowed set' AS detail FROM {ctx.table} WHERE {t} = 'ARRAY' AND len(list_filter("
                f"from_json(json_extract(_raw, '$.{name}'), '[\"VARCHAR\"]'), x -> x IS NULL OR x "
                f"NOT IN {allowed})) > 0"
            )
    return union(ctx, selects)


register(
    Rule(
        "SK-S008",
        "S",
        "Enumerated values allowed",
        "error",
        "Enumerated fields hold one of the values listed in the field dictionary.",
        "Local codes, numeric scales and spelling variants cannot be compared across producers.",
        "Map local codes to the contract enumeration before export.",
        ALL,
        ("severity", "road_class", "quality_flag", "*"),
        "record",
        s008,
        Example("crash_records", {"severity": 2}, {}),
    )
)


def s009(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name in ID_FIELDS:
        if name not in specs(ft):
            continue
        t = q(name + "__t")
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, 'identifier does not match "
            f"{ID_PATTERN}' AS detail FROM {ctx.table} WHERE {t} = 'VARCHAR' AND NOT "
            f"regexp_full_match({q(name)}, '{ID_PATTERN[1:-1]}')"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-S009",
        "S",
        "Identifiers match the pattern",
        "error",
        "Identifiers are 3 to 40 characters of upper case letters, digits, underscore or hyphen.",
        "Case and character set differences make joins fail between producers.",
        "Normalise identifiers to upper case and strip spaces before export.",
        ALL,
        ID_FIELDS,
        "record",
        s009,
        Example("crash_records", {"segment_ref": "seg-dun-010"}, {}),
    )
)


DUPLICATE_KEYS = {
    "crash_records": ("crash_id",),
    "road_segments": ("segment_id",),
    "traffic_counts": ("station_id", "interval_start"),
}


def s010(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    keys = DUPLICATE_KEYS[ft]
    cols = ", ".join(q(k) for k in keys)
    present = " AND ".join(f"{q(k)} IS NOT NULL" for k in keys)
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, '{keys[0]}' AS field, 'identifier already used at row "
            f"' || first_row AS detail FROM (SELECT _row, min(_row) OVER (PARTITION BY {cols}) AS "
            f"first_row FROM {ctx.table} WHERE {present}) WHERE _row > first_row"
        ],
    )


register(
    Rule(
        "SK-S010",
        "S",
        "Identifiers unique within the feed",
        "error",
        "No two records in one feed share the record identifier (station and interval for "
        "counts). Every occurrence after the first is flagged.",
        "Repeated identifiers double count crashes or traffic.",
        "Deduplicate on the identifier before export, keeping the latest version.",
        ALL,
        ("crash_id", "segment_id", "station_id", "interval_start"),
        "record",
        s010,
    )
)


def s011(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name, spec in specs(ft).items():
        if spec.type != "timestamp":
            continue
        t = q(name + "__t")
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, 'not an ISO 8601 UTC timestamp "
            f"ending in Z' AS detail FROM {ctx.table} WHERE {t} IS NOT NULL AND {t} <> 'NULL' "
            f"AND {q(name + '__ts')} IS NULL"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-S011",
        "S",
        "Timestamps are ISO 8601 UTC with Z",
        "error",
        "Timestamp fields are strings such as 2024-03-01T10:15:00Z.",
        "Epoch numbers and local offsets are ambiguous: seconds or milliseconds, UTC or local.",
        "Convert to UTC and format as YYYY-MM-DDTHH:MM:SSZ.",
        ALL,
        ("occurred_at", "reported_at", "interval_start", "valid_from", "valid_to"),
        "record",
        s011,
        Example("crash_records", {"occurred_at": 1684086120}, {}),
    )
)
