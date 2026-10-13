"""Conformance scores per producer and rule family, with Wilson 95 percent intervals.

Definition. A record passes a family when no error or warning rule of that
family flagged it, either directly (row findings) or through its series (a
station flagged by a series rule). Informational findings and file level
findings do not count against records; file level findings are reported
separately as file checks. The overall index is the share of records that
pass every family; it is always shown next to the family scores, never alone.
"""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from sikka.conformance.registry import FAMILY_NAMES
from sikka.core import wilson_interval

COUNTING_SEVERITIES = ("error", "warning")


def _failed_rows(con: duckdb.DuckDBPyConnection, table: str, findings: pd.DataFrame) -> set[int]:
    rows = {int(r) for r in findings["_row"].dropna()}
    series = sorted({str(s) for s in findings.loc[findings["_row"].isna(), "series"].dropna()})
    if series:
        con.register("_series", pd.DataFrame({"s": series}))
        hit = con.execute(
            f"SELECT _row FROM {table} WHERE station_id IN (SELECT s FROM _series)"
        ).fetchall()
        con.unregister("_series")
        rows.update(int(r[0]) for r in hit)
    return rows


def score_rows(
    con: duckdb.DuckDBPyConnection, result: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (scores, file checks) for a :class:`ValidationResult`."""
    per_producer: dict[tuple[str, str], tuple[int, int]] = {}
    overall: dict[str, tuple[int, int]] = {}
    file_checks: list[dict[str, Any]] = []
    for feed in result.validated():
        producer = feed.producer_id or "UNKNOWN"
        total = feed.rows
        failed_any: set[int] = set()
        for family in FAMILY_NAMES:
            outcomes = [
                o
                for o in result.outcomes
                if o.file == feed.file
                and o.rule.family == family
                and o.status == "evaluated"
                and o.rule.severity in COUNTING_SEVERITIES
            ]
            failed: set[int] = set()
            for o in outcomes:
                if o.findings.empty:
                    continue
                if o.rule.scope == "file":
                    file_checks.append(
                        {
                            "file": feed.file,
                            "producer_id": producer,
                            "rule_id": o.rule.id,
                            "findings": len(o.findings),
                        }
                    )
                    continue
                if feed.feed_type is not None:
                    failed |= _failed_rows(con, feed.table, o.findings)
            failed_any |= failed
            passing, n = per_producer.get((producer, family), (0, 0))
            per_producer[(producer, family)] = (passing + total - len(failed), n + total)
        passing, n = overall.get(producer, (0, 0))
        overall[producer] = (passing + total - len(failed_any), n + total)
    scores: list[dict[str, Any]] = []
    for (producer, family), (passing, n) in sorted(per_producer.items()):
        iv = wilson_interval(passing, n)
        scores.append(
            {
                "producer_id": producer,
                "family": family,
                "family_name": FAMILY_NAMES[family],
                "passing": passing,
                "total": n,
                **iv.as_dict(),
            }
        )
    for producer, (passing, n) in sorted(overall.items()):
        iv = wilson_interval(passing, n)
        scores.append(
            {
                "producer_id": producer,
                "family": "ALL",
                "family_name": "All families (overall index)",
                "passing": passing,
                "total": n,
                **iv.as_dict(),
            }
        )
    return scores, file_checks
