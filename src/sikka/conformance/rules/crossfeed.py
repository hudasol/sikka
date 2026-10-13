"""X family: consistency between feeds and between records of one feed."""

from __future__ import annotations

import pandas as pd

from sikka.conformance.context import RuleContext, x_km, y_km
from sikka.conformance.registry import Example, Rule, findings, register
from sikka.conformance.rules.structural import union

CR, RS = ("crash_records",), ("road_segments",)


def _points(table: str, file: str) -> str:
    return (
        f"SELECT '{file}' AS file, _row, epoch(occurred_at__ts) AS ts, {x_km('lon__n')} AS x, "
        f"{y_km('lat__n')} AS y, severity FROM {table} WHERE occurred_at__ts IS NOT NULL AND "
        f"lat__n IS NOT NULL AND lon__n IS NOT NULL"
    )


def _other_points(ctx: RuleContext) -> str | None:
    me = ctx.feed.producer_id
    others = [f for f in ctx.others("crash_records") if f.producer_id != me]
    if not others:
        return None
    return " UNION ALL ".join(_points(f.table, f.file) for f in others)


def x001(ctx: RuleContext) -> pd.DataFrame:
    other = _other_points(ctx)
    if other is None:
        return findings()
    c = ctx.config
    win, km = c.duplicate_minutes * 60, c.duplicate_metres / 1000.0
    return union(
        ctx,
        [
            f"SELECT a._row, NULL AS series, 'crash_id' AS field, 'possible duplicate of ' || "
            f"arg_min(b.file || ' row ' || b._row, abs(a.ts - b.ts)) || ' (' || count(*) || ' "
            f"candidate(s))' AS detail FROM ({_points(ctx.table, ctx.feed.file)}) a JOIN "
            f"({other}) b ON b.ts BETWEEN a.ts - {win} AND a.ts + {win} AND b.x BETWEEN a.x - "
            f"{km} AND a.x + {km} AND b.y BETWEEN a.y - {km} AND a.y + {km} WHERE "
            f"sqrt(power(a.x - b.x, 2) + power(a.y - b.y, 2)) <= {km} GROUP BY a._row"
        ],
    )


register(
    Rule(
        "SK-X001",
        "X",
        "Possible duplicate across producers",
        "info",
        "A crash has a record in another producer's feed within 20 minutes and 200 metres.",
        "The same crash is often reported by several entities. Counting each report would "
        "inflate crash counts; the harmonisation layer resolves these pairs.",
        "No action is needed from the producer; shared identifiers would make matching exact.",
        CR,
        ("crash_id", "occurred_at", "lat", "lon"),
        "record",
        x001,
        needs=("other crash feeds",),
    )
)


def x002(ctx: RuleContext) -> pd.DataFrame:
    other = _other_points(ctx)
    if other is None:
        return findings()
    c = ctx.config
    offset = c.offset_hours * 3600
    tol, win = c.offset_tolerance_minutes * 60, c.duplicate_minutes * 60
    km = c.duplicate_metres / 1000.0
    near = (
        f"b.x BETWEEN a.x - {km} AND a.x + {km} AND b.y BETWEEN a.y - {km} AND a.y + {km} AND "
        f"sqrt(power(a.x - b.x, 2) + power(a.y - b.y, 2)) <= {km}"
    )
    return union(
        ctx,
        [
            f"WITH a AS ({_points(ctx.table, ctx.feed.file)}), b AS ({other}), "
            f"shifted AS (SELECT DISTINCT a._row FROM a JOIN b ON b.ts BETWEEN a.ts - {offset} - "
            f"{tol} AND a.ts - {offset} + {tol} AND {near}), "
            f"matched AS (SELECT DISTINCT a._row FROM a JOIN b ON b.ts BETWEEN a.ts - {win} AND "
            f"a.ts + {win} AND {near}) "
            f"SELECT _row, NULL AS series, 'occurred_at' AS field, 'matches another producer "
            f"record exactly {c.offset_hours:g} hours earlier; local time may be labelled as "
            f"UTC' AS detail FROM shifted WHERE _row NOT IN (SELECT _row FROM matched)"
        ],
    )


register(
    Rule(
        "SK-X002",
        "X",
        "No systematic time offset between producers",
        "warning",
        "A crash that matches another producer's record in place, but only after moving it "
        "four hours earlier, is flagged.",
        "Asia/Dubai is UTC+04:00. Local time labelled as UTC makes the same crash appear four "
        "hours apart in two feeds.",
        "Convert local timestamps to UTC before adding the Z suffix.",
        CR,
        ("occurred_at",),
        "record",
        x002,
        needs=("other crash feeds",),
    )
)


def x003(ctx: RuleContext) -> pd.DataFrame:
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


register(
    Rule(
        "SK-X003",
        "X",
        "No near duplicate within the feed",
        "warning",
        "Two records of one feed within 5 minutes and 50 metres with the same severity are "
        "flagged; the later report is the one marked.",
        "A crash entered twice, with or without a new identifier, is counted twice.",
        "Deduplicate at the source; keep one record per crash and update it in place.",
        CR,
        ("crash_id",),
        "record",
        x003,
    )
)


def x004(ctx: RuleContext) -> pd.DataFrame:
    if not ctx.has_registry:
        return findings()
    file = ctx.feed.file.replace("'", "''")
    checks = []
    for key, other in (
        ("road_name_ar", "road_name_en"),
        ("road_name_en", "road_name_ar"),
        ("segment_id", "road_name_en"),
        ("segment_id", "road_name_ar"),
    ):
        checks.append(
            f"SELECT _row, NULL AS series, '{other}' AS field, '{other} differs from the usual "
            f"name ' || usual || ' for the same {key}' AS detail FROM (SELECT _row, file, {other} "
            f"AS v, mode({other}) OVER (PARTITION BY {key}) AS usual, count(DISTINCT {other}) "
            f"OVER (PARTITION BY {key}) AS k FROM reg_all WHERE {key} IS NOT NULL AND {other} IS "
            f"NOT NULL) WHERE file = '{file}' AND k > 1 AND v <> usual"
        )
    frame = union(ctx, checks)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["_row", "field"]).reset_index(drop=True)


register(
    Rule(
        "SK-X004",
        "X",
        "Consistent road names",
        "warning",
        "One Arabic name maps to one English name and the reverse, and a segment has one "
        "name across registry feeds. Rows that differ from the usual name are flagged.",
        "Inconsistent naming splits one road into several in search and in reports.",
        "Agree a bilingual road name list between producers and use it in every feed.",
        RS,
        ("road_name_en", "road_name_ar"),
        "record",
        x004,
        Example("road_segments", {"road_name_ar": "Dune Corridor"}, {}),
        needs=("registry",),
    )
)


def x005(ctx: RuleContext) -> pd.DataFrame:
    counts = ctx.all_of("traffic_counts")
    if not ctx.has_registry or not counts:
        return findings()
    header = ctx.feed.header or {}
    start, end = header.get("period_start"), header.get("period_end")
    years = 5.0
    if isinstance(start, str) and isinstance(end, str):
        span = ctx.sql(
            f"SELECT date_diff('day', TRY_CAST(replace('{start}', 'Z', '') AS TIMESTAMP), "
            f"TRY_CAST(replace('{end}', 'Z', '') AS TIMESTAMP)) AS d"
        )
        if not span.empty and span["d"][0] is not None and span["d"][0] > 0:
            years = float(span["d"][0]) / 365.25
    flows = " UNION ALL ".join(
        f"SELECT segment_ref, vehicle_count__n AS n, interval_start__ts AS ts FROM {f.table} "
        f"WHERE vehicle_count__n >= 0"
        for f in counts
    )
    factor = ctx.config.exposure_rate_factor
    return union(
        ctx,
        [
            f"WITH aadt AS (SELECT segment_ref, sum(n) / greatest(1, count(DISTINCT CAST(ts AS "
            f"DATE))) AS aadt FROM ({flows}) GROUP BY segment_ref), crashes AS (SELECT "
            f"segment_ref, count(*) / {years} AS per_year FROM {ctx.table} WHERE segment_ref IS "
            f"NOT NULL GROUP BY segment_ref), rates AS (SELECT c.segment_ref, c.per_year / "
            f"(a.aadt * 365 * s.length_m / 1000 / 1e6) AS rate FROM crashes c JOIN aadt a USING "
            f"(segment_ref) JOIN reg_segments s ON s.segment_id = c.segment_ref WHERE a.aadt > 0), "
            f"med AS (SELECT median(rate) AS m FROM rates) SELECT t._row, NULL AS series, "
            f"'segment_ref' AS field, 'crash rate on this segment is ' || round(r.rate / med.m, "
            f"1) || ' times the median; check exposure or the segment reference' AS detail FROM "
            f"{ctx.table} t JOIN rates r ON r.segment_ref = t.segment_ref, med WHERE r.rate > "
            f"{factor} * med.m"
        ],
    )


register(
    Rule(
        "SK-X005",
        "X",
        "Crash counts plausible for the exposure",
        "warning",
        "Crashes per million vehicle kilometres on a segment are below 20 times the median "
        "across segments with counts.",
        "An extreme rate usually means wrong exposure (a broken station) or crashes assigned "
        "to the wrong segment, not a real hazard.",
        "Check the station feeding the segment and the crash segment references.",
        CR,
        ("segment_ref",),
        "record",
        x005,
        needs=("registry", "traffic counts"),
    )
)
