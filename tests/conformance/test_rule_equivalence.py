"""Faster forms of SK-X003 and SK-P002 must flag exactly what the plain forms flag."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sikka.conformance import BASE_RECORDS, RuleContext, Source, run_validation
from sikka.conformance.context import x_km, y_km
from sikka.conformance.rules.privacy import p002
from sikka.conformance.rules.structural import union
from sikka.core import format_utc

from .helpers import feed_bytes, header, registry_source

SLOW = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _context(data: bytes) -> tuple[Any, RuleContext]:
    result = run_validation([Source.from_bytes("feed.ndjson", data)], [registry_source()])
    feed = result.feeds[0]
    ctx = RuleContext(result.con, feed, result.feeds, has_registry=True)
    return result, ctx


def _rows(frame: pd.DataFrame) -> set[tuple[int, str]]:
    return {(int(r), str(f)) for r, f in zip(frame["_row"], frame["field"], strict=True)}


def _plain_x003(ctx: RuleContext) -> pd.DataFrame:
    """SK-X003 as first written: a join on ranges only."""
    c = ctx.config
    win, km = c.within_feed_minutes * 60, c.within_feed_metres / 1000.0
    pts = (
        f"SELECT _row, epoch(occurred_at__ts) AS ts, epoch(reported_at__ts) AS rts, "
        f"{x_km('lon__n')} AS x, {y_km('lat__n')} AS y, severity FROM {ctx.table} WHERE "
        f"occurred_at__ts IS NOT NULL AND lat__n IS NOT NULL AND lon__n IS NOT NULL"
    )
    return union(
        ctx,
        [
            f"SELECT a._row, NULL AS series, 'crash_id' AS field, 'near duplicate of row ' || "
            f"min(b._row) AS detail FROM ({pts}) a JOIN ({pts}) b ON b.ts BETWEEN a.ts - {win} "
            f"AND a.ts + {win} AND b.x BETWEEN a.x - {km} AND a.x + {km} AND b.y BETWEEN a.y - "
            f"{km} AND a.y + {km} AND a.severity IS NOT DISTINCT FROM b.severity AND "
            f"(coalesce(b.rts, 0), b._row) < (coalesce(a.rts, 0), a._row) WHERE "
            f"sqrt(power(a.x - b.x, 2) + power(a.y - b.y, 2)) <= {km} GROUP BY a._row"
        ],
    )


crash_points = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=40),  # minutes after a base time, crossing buckets
        st.integers(min_value=0, max_value=120),  # metres north
        st.sampled_from(["minor_injury", "serious_injury", None]),
        st.integers(min_value=0, max_value=180),  # reporting delay in minutes
    ),
    min_size=1,
    max_size=14,
)


@SLOW
@given(crash_points)
def test_x003_bucketed_join_matches_the_range_join(points: list[tuple[int, int, Any, int]]) -> None:
    base = datetime(2023, 5, 14, 17, 2, 30, tzinfo=UTC)
    records = []
    for i, (minutes, north, severity, delay) in enumerate(points, 1):
        occurred = base + timedelta(minutes=minutes)
        record: dict[str, Any] = dict(BASE_RECORDS["crash_records"]) | {
            "crash_id": f"PB-{i:07d}",
            "occurred_at": format_utc(occurred),
            "reported_at": format_utc(occurred + timedelta(minutes=delay)),
            "lat": round(23.543057 + north / 110574.0, 6),
        }
        if severity is None:
            record.pop("severity")
        else:
            record["severity"] = severity
        records.append(record)
    result, ctx = _context(feed_bytes("crash_records", records))
    try:
        from sikka.conformance.rules.crossfeed import x003

        fast, plain = x003(ctx), _plain_x003(ctx)
        assert set(fast["_row"]) == set(plain["_row"])
        assert sorted(fast["detail"]) == sorted(plain["detail"])
    finally:
        result.close()


def _raw_feed(lines: list[str]) -> bytes:
    head = header("crash_records", record_count=len(lines))
    return ("\n".join([json.dumps({"sikka_header": head}), *lines]) + "\n").encode("utf-8")


def _line(**fields: Any) -> str:
    return json.dumps(dict(BASE_RECORDS["crash_records"]) | fields, ensure_ascii=False)


def test_p002_prefilter_keeps_escaped_and_exponent_values() -> None:
    lines = [
        _line(crash_id="PB-0000001"),
        # The email's @ written as a JSON escape: the raw line has no @ at all.
        _line(crash_id="PB-0000002", note="x").replace('"x"', '"someone\\u0040example.com"'),
        # A phone number with an escaped digit.
        _line(crash_id="PB-0000003", note="x").replace('"x"', '"+97150\\u0031234567"'),
        # A number in exponent form that decodes to an identity card shaped value.
        _line(crash_id="PB-0000004", note=0).replace('"note": 0', '"note": 7.84123412345678e14'),
        _line(crash_id="PB-0000005", contact={"phone": "0501234567"}),
        _line(crash_id="PB-0000006", refs=["a", "784-1234-1234567-1"]),
        _line(crash_id="PB-0000007", weather="clear"),
    ]
    result, ctx = _context(_raw_feed(lines))
    try:
        fast, plain = p002(ctx), p002(ctx, prefilter=False)
        assert _rows(fast) == _rows(plain)
        assert {r for r, _ in _rows(fast)} == {2, 3, 4, 5, 6}
    finally:
        result.close()


values = st.recursive(
    st.one_of(
        st.text(alphabet="0123456789 -+@.abcE\\u", max_size=24),
        st.integers(min_value=-(10**15), max_value=10**16),
        st.floats(allow_nan=False, allow_infinity=False),
        st.none(),
        st.booleans(),
    ),
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.sampled_from("pq"), inner),
    max_leaves=6,
)


@SLOW
@given(st.lists(st.dictionaries(st.sampled_from(["note", "ref", "extra"]), values), max_size=6))
def test_p002_prefilter_matches_the_full_scan(extras: list[dict[str, Any]]) -> None:
    lines = [_line(crash_id=f"PB-{i:07d}", **e) for i, e in enumerate(extras, 1)]
    lines = lines or [_line()]
    result, ctx = _context(_raw_feed(lines))
    try:
        assert _rows(p002(ctx)) == _rows(p002(ctx, prefilter=False))
    finally:
        result.close()
