"""T family: completeness of time series and timeliness of reporting."""

from __future__ import annotations

import math

import pandas as pd

from sikka.conformance.context import RuleContext
from sikka.conformance.registry import Example, Rule, findings, register
from sikka.conformance.rules.structural import file_finding, union

CR, TC = ("crash_records",), ("traffic_counts",)


def _period(ctx: RuleContext) -> tuple[str, str] | None:
    header = ctx.feed.header or {}
    start, end = header.get("period_start"), header.get("period_end")
    if (
        isinstance(start, str)
        and isinstance(end, str)
        and start.endswith("Z")
        and end.endswith("Z")
    ):
        return (
            f"TRY_CAST(replace('{start}', 'Z', '') AS TIMESTAMP)",
            f"TRY_CAST(replace('{end}', 'Z', '') AS TIMESTAMP)",
        )
    return None


def t001(ctx: RuleContext) -> pd.DataFrame:
    period = _period(ctx)
    if period is None:
        bounds = (
            "min(interval_start__ts) OVER w",
            "max(interval_start__ts) OVER w + INTERVAL 1 SECOND",
        )
    else:
        bounds = period
    frame = ctx.sql(
        f"SELECT station_id, any_value(m) AS m, count(DISTINCT slot) AS present, "
        f"any_value(expected) AS expected FROM (SELECT station_id, m, time_bucket(to_minutes("
        f"m::BIGINT), interval_start__ts) AS slot, (epoch({bounds[1]}) - epoch({bounds[0]})) / "
        f"(m * 60) AS expected, interval_start__ts AS ts, {bounds[0]} AS lo, {bounds[1]} AS hi "
        f"FROM (SELECT *, mode(interval_minutes__n) OVER (PARTITION BY station_id) AS m FROM "
        f"{ctx.table} WHERE station_id IS NOT NULL AND interval_start__ts IS NOT NULL AND "
        f"interval_minutes__n > 0) WINDOW w AS (PARTITION BY station_id)) WHERE ts >= lo AND "
        f"ts < hi GROUP BY station_id ORDER BY station_id"
    )
    rows = []
    for station, _, present, expected in frame.itertuples(index=False):
        missing = math.floor(float(expected) + 1e-9) - int(present)
        if missing > 0:
            rows.append(
                {
                    "_row": None,
                    "series": station,
                    "field": "interval_start",
                    "detail": f"{missing} of {math.floor(float(expected))} intervals missing",
                }
            )
    return findings(rows)


register(
    Rule(
        "SK-T001",
        "T",
        "No gaps in station time series",
        "warning",
        "Each station reports every interval of the declared period.",
        "Gaps bias daily traffic estimates downward unless they are known and corrected.",
        "Backfill from the station buffer, or flag the interval as estimated.",
        TC,
        ("interval_start",),
        "series",
        t001,
    )
)


def t002(ctx: RuleContext) -> pd.DataFrame:
    days = ctx.config.late_days
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, 'reported_at' AS field, 'reported ' || "
            f"date_diff('day', occurred_at__ts, reported_at__ts) || ' days after the crash' AS "
            f"detail FROM {ctx.table} WHERE reported_at__ts - occurred_at__ts > INTERVAL "
            f"{int(days)} DAY"
        ],
    )


register(
    Rule(
        "SK-T002",
        "T",
        "Records arrive on time",
        "warning",
        "A crash is reported within 30 days of occurring.",
        "Late records change past counts after they have been used for ranking.",
        "Send records as they are created, and send corrections as updates.",
        CR,
        ("reported_at",),
        "record",
        t002,
        Example("crash_records", {"reported_at": "2024-06-01T00:00:00Z"}, {}),
    )
)


def t003(ctx: RuleContext) -> pd.DataFrame:
    period = _period(ctx)
    if period is None:
        return findings()
    local = "interval 4 hour"
    frame = ctx.sql(
        f"WITH months AS (SELECT strftime(m, '%Y-%m') AS month FROM (SELECT unnest(generate_series("
        f"date_trunc('month', {period[0]} + {local}), date_trunc('month', {period[1]} + {local} - "
        f"INTERVAL 1 SECOND), INTERVAL 1 MONTH)) AS m)), seen AS (SELECT strftime("
        f"occurred_at__ts + {local}, '%Y-%m') AS month, count(*) AS n FROM {ctx.table} WHERE "
        f"occurred_at__ts IS NOT NULL GROUP BY 1) SELECT months.month, coalesce(seen.n, 0) AS n "
        f"FROM months LEFT JOIN seen USING (month) ORDER BY months.month"
    )
    if frame.empty:
        return findings()
    typical = float(frame["n"].median())
    if typical <= 0 or math.exp(-typical) >= ctx.config.zero_month_p:
        return findings()
    empty = frame.loc[frame["n"] == 0, "month"].tolist()
    if not empty:
        return findings()
    return file_finding(
        f"no records in {len(empty)} month(s) of the declared period: {', '.join(empty)}; "
        f"a typical month has {typical:g}",
        "occurred_at",
    )


register(
    Rule(
        "SK-T003",
        "T",
        "Every month of the period covered",
        "warning",
        "No calendar month (local time) of the declared period is empty when a typical month "
        "has enough records that an empty one is very unlikely by chance (probability below "
        "0.001 under a Poisson model).",
        "Missing months make a segment look safer than it is.",
        "Resend the missing months or shorten the declared period.",
        CR,
        ("occurred_at",),
        "file",
        t003,
    )
)


def t004(ctx: RuleContext) -> pd.DataFrame:
    period = _period(ctx)
    if period is None:
        return findings()
    field = "occurred_at" if ctx.feed.feed_type == "crash_records" else "interval_start"
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, '{field}' AS field, 'outside the declared period' AS "
            f"detail FROM {ctx.table} WHERE {field}__ts < {period[0]} OR {field}__ts >= "
            f"{period[1]}"
        ],
    )


register(
    Rule(
        "SK-T004",
        "T",
        "Records inside the declared period",
        "warning",
        "Each record's time lies inside the header period_start (inclusive) and period_end "
        "(exclusive).",
        "Records outside the period are double counted when consecutive files are combined.",
        "Filter records to the declared period on export, or widen the period.",
        CR + TC,
        ("occurred_at", "interval_start"),
        "record",
        t004,
        Example(
            "crash_records",
            {"occurred_at": "2019-05-14T17:42:00Z", "reported_at": "2019-05-14T19:05:00Z"},
            {},
        ),
    )
)
