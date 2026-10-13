"""Feed profiling: row counts, presence and null rates, ranges, distinct values, time coverage."""

from __future__ import annotations

from typing import Any

import duckdb

from sikka.ingest.parsers import contract_types
from sikka.ingest.staging import StagedFeed, _quote

ENUM_TOP = 8


def profile_feed(con: duckdb.DuckDBPyConnection, feed: StagedFeed) -> dict[str, Any]:
    """Summary statistics computed in DuckDB. Values of free text are never included."""
    invalid = con.execute(f"SELECT count(*) FROM {feed.table}_invalid").fetchone()
    out: dict[str, Any] = {
        "file": feed.file,
        "format": feed.fmt,
        "feed_type": feed.feed_type,
        "rows": feed.rows,
        "invalid_json_rows": int(invalid[0]) if invalid else 0,
        "fields": [],
    }
    if feed.feed_type is None or feed.rows == 0:
        return out
    table = feed.table
    for field, kind in contract_types(feed.feed_type).items():
        f, t = _quote(field), _quote(field + "__t")
        row = con.execute(
            f"SELECT count({t}), count(*) FILTER (WHERE {t} = 'NULL'), "
            f"count(DISTINCT {f}) FROM {table}"
        ).fetchone()
        present, nulls, distinct = (int(v) for v in row) if row else (0, 0, 0)
        stats: dict[str, Any] = {
            "field": field,
            "type": kind,
            "present_share": present / feed.rows if feed.rows else 0.0,
            "null_count": nulls,
            "distinct": distinct,
        }
        if kind in {"number", "integer"}:
            lo, hi = con.execute(
                f"SELECT min({_quote(field + '__n')}), max({_quote(field + '__n')}) FROM {table}"
            ).fetchone() or (None, None)
            stats["min"], stats["max"] = lo, hi
        if kind == "timestamp":
            lo, hi = con.execute(
                f"SELECT strftime(min({_quote(field + '__ts')}), '%Y-%m-%dT%H:%M:%SZ'), "
                f"strftime(max({_quote(field + '__ts')}), '%Y-%m-%dT%H:%M:%SZ') FROM {table}"
            ).fetchone() or (None, None)
            stats["first"], stats["last"] = lo, hi
        if kind == "enum":
            top = con.execute(
                f"SELECT {f}, count(*) AS n FROM {table} WHERE {f} IS NOT NULL "
                f"GROUP BY {f} ORDER BY n DESC, {f} LIMIT {ENUM_TOP}"
            ).fetchall()
            stats["top_values"] = [{"value": v, "count": int(n)} for v, n in top]
        out["fields"].append(stats)
    return out
