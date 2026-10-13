"""Stage parsed feeds into DuckDB in batches, then expose typed columns.

Each feed becomes two tables: ``<key>_raw`` with the row number and the raw
JSON text, and ``<key>`` with one group of columns per contract field:

* ``"f"``      the value as text (``json_extract_string``),
* ``"f__t"``   its JSON type (``UBIGINT``, ``BIGINT``, ``DOUBLE``, ``VARCHAR``, ...),
  or NULL when the field is absent,
* ``"f__n"``   a DOUBLE when the JSON value is a number,
* ``"f__ts"``  a TIMESTAMP when the value is an ISO 8601 UTC string with ``Z``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import duckdb
import pandas as pd

from sikka.contract import UTC_TIMESTAMP_PATTERN
from sikka.ingest.parsers import ParsedFeed, contract_types

BATCH_ROWS = 100_000
NUMERIC_JSON_TYPES = ("UBIGINT", "BIGINT", "DOUBLE")


@dataclass
class StagedFeed:
    key: str
    file: str
    fmt: str
    feed_type: str | None
    header: dict[str, Any] | None
    header_error: str | None
    rows: int
    content_hash: str
    is_reference: bool = False

    @property
    def table(self) -> str:
        return self.key

    @property
    def producer_id(self) -> str | None:
        if self.header and isinstance(self.header.get("producer_id"), str):
            return str(self.header["producer_id"])
        return None


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def json_path(field: str) -> str:
    return "$." + ".".join(f'"{part}"' for part in field.split("."))


def typed_columns(feed_type: str | None) -> list[str]:
    """SQL select list for the typed table of a feed type.

    It reads from :func:`typed_source`, which parses each line once and extracts every
    contract path into the lists ``_s`` (values as text) and ``_t`` (JSON types).
    """
    cols = ["_row", "_raw", "json_keys(_raw) AS _keys"]
    if feed_type is None:
        return cols
    ts_regex = UTC_TIMESTAMP_PATTERN.replace("'", "''")
    for i, (field, kind) in enumerate(contract_types(feed_type).items(), 1):
        name = field
        t = f"_t[{i}]"
        s = f"_s[{i}]"
        cols.append(f"{s} AS {_quote(name)}")
        cols.append(f"{t} AS {_quote(name + '__t')}")
        if kind in {"number", "integer"}:
            cols.append(
                f"CASE WHEN {t} IN {NUMERIC_JSON_TYPES} THEN TRY_CAST({s} AS DOUBLE) END "
                f"AS {_quote(name + '__n')}"
            )
        if kind == "timestamp":
            cols.append(
                f"CASE WHEN {t} = 'VARCHAR' AND regexp_matches({s}, '{ts_regex}') "
                f"THEN TRY_CAST(replace({s}, 'Z', '') AS TIMESTAMP) END "
                f"AS {_quote(name + '__ts')}"
            )
    return cols


def typed_source(feed_type: str | None, raw_table: str) -> str:
    """Valid rows of ``raw_table`` with every contract path extracted in one parse."""
    if feed_type is None:
        return f"SELECT _row, _raw FROM {raw_table} WHERE json_valid(_raw)"
    paths = ", ".join(
        "'" + json_path(f).replace("'", "''") + "'" for f in contract_types(feed_type)
    )
    return (
        f"SELECT _row, _raw, json_extract_string(_raw, [{paths}]) AS _s, "
        f"json_type(_raw, [{paths}]) AS _t FROM {raw_table} WHERE json_valid(_raw)"
    )


def stage(
    con: duckdb.DuckDBPyConnection, parsed: ParsedFeed, key: str, *, is_reference: bool = False
) -> StagedFeed:
    """Stream a parsed feed into DuckDB. Memory use is bounded by ``BATCH_ROWS``."""
    raw = f"{key}_raw"
    con.execute(f"CREATE OR REPLACE TABLE {raw} (_row INTEGER, _raw VARCHAR)")
    digest = hashlib.sha256()
    if parsed.header is not None:
        digest.update(repr(sorted(parsed.header.items())).encode("utf-8"))
    batch_rows: list[int] = []
    batch_raw: list[str] = []
    n = 0

    def flush() -> None:
        if not batch_rows:
            return
        frame = pd.DataFrame({"_row": batch_rows, "_raw": batch_raw})
        con.register("_batch", frame)
        con.execute(f"INSERT INTO {raw} SELECT _row, _raw FROM _batch")
        con.unregister("_batch")
        batch_rows.clear()
        batch_raw.clear()

    for text in parsed.rows:
        n += 1
        digest.update(text.encode("utf-8"))
        digest.update(b"\n")
        batch_rows.append(n)
        batch_raw.append(text)
        if len(batch_rows) >= BATCH_ROWS:
            flush()
    flush()
    select = ", ".join(typed_columns(parsed.feed_type))
    source = typed_source(parsed.feed_type, raw)
    con.execute(f"CREATE OR REPLACE TABLE {key} AS SELECT {select} FROM ({source})")
    con.execute(
        f"CREATE OR REPLACE TABLE {key}_invalid AS SELECT _row FROM {raw} "
        "WHERE NOT json_valid(_raw)"
    )
    con.execute(f"DROP TABLE {raw}")
    return StagedFeed(
        key=key,
        file=parsed.name,
        fmt=parsed.fmt,
        feed_type=parsed.feed_type,
        header=parsed.header,
        header_error=parsed.header_error,
        rows=n,
        content_hash=digest.hexdigest(),
        is_reference=is_reference,
    )
