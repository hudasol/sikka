"""V family: values that are well formed but implausible or in the wrong unit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sikka.conformance.context import RuleContext
from sikka.conformance.fields import specs
from sikka.conformance.registry import Example, Rule, findings, register
from sikka.conformance.rules.structural import ALL, q, sql_list, union
from sikka.contract import UAE_BBOX

CR, TC, RS = ("crash_records",), ("traffic_counts",), ("road_segments",)
B = UAE_BBOX
ARABIC_DIGITS = f"[{chr(0x0660)}-{chr(0x0669)}{chr(0x06F0)}-{chr(0x06F9)}]"
ARABIC_LETTERS = f"[{chr(0x0621)}-{chr(0x064A)}]"
NEGATIVE_SENTINELS = (-1, -9, -99, -999)
LARGE_SENTINELS = (9999, 99999)
TEXT_SENTINELS = ("N/A", "NA", "n/a", "null", "NULL", "-", "")


def v001(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name, spec in specs(ft).items():
        if spec.type not in {"number", "integer"}:
            continue
        n = q(name + "__n")
        conds = []
        if spec.minimum is not None:
            exclusive = (spec.allowed or "").startswith("greater than")
            conds.append(f"{n} {'<=' if exclusive else '<'} {spec.minimum}")
        if spec.maximum is not None:
            conds.append(f"{n} > {spec.maximum}")
        if not conds:
            continue
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, 'value ' || {n} || ' outside "
            f"{spec.allowed}' AS detail FROM {ctx.table} WHERE {n} IS NOT NULL AND "
            f"({' OR '.join(conds)})"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-V001",
        "V",
        "Numeric values inside contract ranges",
        "error",
        "Numbers lie inside the range given in the field dictionary, for example counts are "
        "not negative and occupancy is at most 100.",
        "Out of range values are impossible by definition and usually come from sign or unit "
        "errors.",
        "Check the sign convention and the unit of the source system.",
        ALL,
        ("vehicle_count", "occupancy_pct", "mean_speed_kmh", "vehicles_involved", "*"),
        "record",
        v001,
        Example("traffic_counts", {"vehicle_count": -40}, {}),
    )
)


def v002(ctx: RuleContext) -> pd.DataFrame:
    c = ctx.config
    limit = "s.speed_limit_kmh" if ctx.has_registry else "NULL"
    join = (
        f"LEFT JOIN reg_segments s ON s.segment_id = t.{q('segment_ref')}"
        if ctx.has_registry
        else ""
    )
    return union(
        ctx,
        [
            f"SELECT t._row, NULL AS series, 'mean_speed_kmh' AS field, 'mean speed ' || "
            f"t.mean_speed_kmh__n || ' km/h is not plausible' AS detail FROM {ctx.table} t {join} "
            f"WHERE t.mean_speed_kmh__n > {c.speed_absolute_max} OR t.mean_speed_kmh__n > "
            f"{c.speed_ratio_max} * {limit}"
        ],
    )


register(
    Rule(
        "SK-V002",
        "V",
        "Speeds plausible",
        "error",
        "Mean interval speed is below 200 km/h and below 1.6 times the posted limit of the "
        "segment.",
        "A mean over many vehicles far above the limit points to a unit or sensor error.",
        "Check the speed unit and the detector calibration.",
        TC,
        ("mean_speed_kmh",),
        "record",
        v002,
        Example("traffic_counts", {"mean_speed_kmh": 310.0}, {}),
        needs=("registry",),
    )
)


def _outside(lat: str, lon: str) -> str:
    return (
        f"({lat} < {B['lat_min']} OR {lat} > {B['lat_max']} OR {lon} < {B['lon_min']} OR "
        f"{lon} > {B['lon_max']})"
    )


def v003(ctx: RuleContext) -> pd.DataFrame:
    if ctx.feed.feed_type == "road_segments":
        return union(
            ctx,
            [
                f"SELECT _row, NULL AS series, 'geometry.coordinates' AS field, 'vertex outside "
                f"the UAE bounding box' AS detail FROM (SELECT _row, unnest(from_json("
                f"json_extract(_raw, '$.geometry.coordinates'), '[[\"DOUBLE\"]]')) AS p FROM "
                f"{ctx.table} WHERE {q('geometry.coordinates__t')} = 'ARRAY') WHERE "
                f"{_outside('p[2]', 'p[1]')} GROUP BY _row"
            ],
        )
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, 'lat' AS field, 'position ' || lat__n || ', ' || "
            f"lon__n || ' is outside the UAE bounding box' AS detail FROM {ctx.table} WHERE "
            f"lat__n IS NOT NULL AND lon__n IS NOT NULL AND {_outside('lat__n', 'lon__n')}"
        ],
    )


register(
    Rule(
        "SK-V003",
        "V",
        "Coordinates inside the UAE bounding box",
        "error",
        f"Latitude lies in {B['lat_min']} to {B['lat_max']} and longitude in {B['lon_min']} to "
        f"{B['lon_max']}.",
        "Points outside the country cannot belong to the network: zero coordinates, sign "
        "errors and swapped axes all land here.",
        "Check the coordinate reference system and the order of latitude and longitude.",
        CR + RS,
        ("lat", "lon", "geometry.coordinates"),
        "record",
        v003,
        Example("crash_records", {"lat": 0.0, "lon": 0.0}, {}),
    )
)


def v004(ctx: RuleContext) -> pd.DataFrame:
    inside_swapped = (
        f"lon__n BETWEEN {B['lat_min']} AND {B['lat_max']} AND lat__n BETWEEN {B['lon_min']} "
        f"AND {B['lon_max']}"
    )
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, 'lat' AS field, 'latitude and longitude appear "
            f"swapped' AS detail FROM {ctx.table} WHERE {_outside('lat__n', 'lon__n')} AND "
            f"{inside_swapped}"
        ],
    )


register(
    Rule(
        "SK-V004",
        "V",
        "Latitude and longitude not swapped",
        "error",
        "A point outside the bounding box that would fall inside it with the axes exchanged is "
        "reported as swapped.",
        "GeoJSON orders positions as longitude, latitude while many tables use the opposite; "
        "mixing the two is common.",
        "Write lat as the north south coordinate (about 22 to 27 in the UAE) and lon as the "
        "east west one (about 51 to 57).",
        CR,
        ("lat", "lon"),
        "record",
        v004,
        Example("crash_records", {"lat": 53.443151, "lon": 23.543057}, {}),
    )
)


def v005(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = [
        f"SELECT _row, NULL AS series, '{name}' AS field, 'value contains Arabic Indic digits' "
        f"AS detail FROM {ctx.table} WHERE regexp_matches({q(name)}, '{ARABIC_DIGITS}')"
        for name, spec in specs(ft).items()
        if spec.type not in {"object", "list of positions"}
    ]
    return union(ctx, selects)


register(
    Rule(
        "SK-V005",
        "V",
        "Digits are ASCII",
        "error",
        "Numbers, identifiers and timestamps use the digits 0 to 9.",
        "Arabic Indic digits are correct in Arabic text but are not parsed as numbers by most "
        "systems, so values silently become missing.",
        "Convert digits to ASCII on export; keep Arabic Indic digits for display only.",
        ALL,
        ("vehicles_involved", "lat", "vehicle_count", "*"),
        "record",
        v005,
        Example("crash_records", {"vehicles_involved": chr(0x0662)}, {}),
    )
)


def v006(ctx: RuleContext) -> pd.DataFrame:
    ft = ctx.feed.feed_type
    assert ft is not None
    selects = []
    for name, spec in specs(ft).items():
        if spec.type in {"number", "integer"}:
            values = list(NEGATIVE_SENTINELS)
            if spec.maximum is not None and spec.maximum < 9999:
                values += list(LARGE_SENTINELS)
            cond = f"{q(name + '__n')} IN ({', '.join(str(v) for v in values)})"
        elif spec.type in {"string", "identifier", "enum", "timestamp"}:
            cond = f"{q(name + '__t')} = 'VARCHAR' AND {q(name)} IN {sql_list(TEXT_SENTINELS)}"
        else:
            continue
        selects.append(
            f"SELECT _row, NULL AS series, '{name}' AS field, 'value looks like a placeholder "
            f"for missing data' AS detail FROM {ctx.table} WHERE {cond}"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-V006",
        "V",
        "No sentinel values for missing data",
        "warning",
        "Values such as -1, -999, 9999, N/A or an empty string are not used to mean missing.",
        "The contract says missing values are absent. Sentinels look like real values and bias "
        "averages.",
        "Leave the field out when the value is unknown.",
        ALL,
        ("*",),
        "record",
        v006,
        Example("traffic_counts", {"mean_speed_kmh": -1}, {}),
    )
)


def v007(ctx: RuleContext) -> pd.DataFrame:
    generated = (ctx.feed.header or {}).get("generated_at")
    selects = [
        f"SELECT _row, NULL AS series, 'reported_at' AS field, 'reported before it occurred' "
        f"AS detail FROM {ctx.table} WHERE reported_at__ts < occurred_at__ts"
    ]
    if isinstance(generated, str) and generated.endswith("Z"):
        selects.append(
            f"SELECT _row, NULL AS series, 'occurred_at' AS field, 'occurred after the file was "
            f"generated' AS detail FROM {ctx.table} WHERE occurred_at__ts > TRY_CAST("
            f"replace('{generated}', 'Z', '') AS TIMESTAMP)"
        )
    return union(ctx, selects)


register(
    Rule(
        "SK-V007",
        "V",
        "Timestamps in a sensible order",
        "error",
        "A crash is reported at or after it occurred, and occurred before the file was generated.",
        "Reversed order points to time zone handling errors or swapped fields.",
        "Check that both timestamps are converted to UTC the same way.",
        CR,
        ("occurred_at", "reported_at"),
        "record",
        v007,
        Example("crash_records", {"reported_at": "2023-05-14T16:00:00Z"}, {}),
    )
)


def _station_frame(ctx: RuleContext) -> pd.DataFrame:
    lanes = "coalesce(s.lane_count, 2)" if ctx.has_registry else "2"
    limit = "s.speed_limit_kmh" if ctx.has_registry else "NULL"
    join = (
        f"LEFT JOIN reg_segments s ON s.segment_id = t.{q('segment_ref')}"
        if ctx.has_registry
        else ""
    )
    return ctx.sql(
        f"SELECT t._row, t.station_id, t.vehicle_count__n AS n, t.mean_speed_kmh__n AS v, "
        f"t.occupancy_pct__n AS occ, {lanes} AS lanes, {limit} AS lim FROM {ctx.table} t {join} "
        f"WHERE t.station_id IS NOT NULL"
    )


def _flag_stations(frame: pd.DataFrame, bad: list[str], field: str, detail: str) -> pd.DataFrame:
    hit = frame[frame["station_id"].isin(bad)]
    return findings(
        [
            {"_row": int(r), "series": s, "field": field, "detail": detail}
            for r, s in zip(hit["_row"], hit["station_id"], strict=True)
        ]
    )


def v008(ctx: RuleContext) -> pd.DataFrame:
    frame = _station_frame(ctx)
    if frame.empty:
        return findings()
    c = ctx.config
    stats = frame.groupby("station_id").agg(
        v=("v", "median"), occ=("occ", "median"), lim=("lim", "median")
    )
    lim = stats["lim"].fillna(80.0)
    bad = stats[(stats["v"] < c.ms_speed_ratio * lim) & (stats["occ"] < c.ms_occupancy_max)]
    return _flag_stations(
        frame,
        sorted(bad.index),
        "mean_speed_kmh",
        "free flowing station reports speeds below half the limit; likely metres per second",
    )


register(
    Rule(
        "SK-V008",
        "V",
        "Speed unit plausible",
        "warning",
        "At a station with low occupancy (free flow), the median speed is at least half the "
        "posted limit.",
        "Free flowing traffic near the limit reported at a third of it is the signature of "
        "metres per second.",
        "Multiply by 3.6 if the source reports m/s, and fix the export unit.",
        TC,
        ("mean_speed_kmh",),
        "series",
        v008,
        needs=("registry",),
    )
)


def v009(ctx: RuleContext) -> pd.DataFrame:
    frame = _station_frame(ctx)
    if frame.empty:
        return findings()
    frame = frame.assign(
        expected=(frame["n"] / frame["lanes"]) * 6.5 / (frame["v"].clip(lower=1) * 1000) * 100
    )
    frame = frame.assign(ratio=frame["occ"] / frame["expected"].where(frame["expected"] > 0.05))
    stats = frame.groupby("station_id").agg(ratio=("ratio", "median"), top=("occ", "max"))
    bad = stats[(stats["top"] <= 1.0) & (stats["ratio"] < ctx.config.fraction_ratio_max)]
    return _flag_stations(
        frame,
        sorted(bad.index),
        "occupancy_pct",
        "occupancy is about a hundredth of what the flow implies; likely a fraction, not percent",
    )


register(
    Rule(
        "SK-V009",
        "V",
        "Occupancy unit plausible",
        "warning",
        "Occupancy agrees in order of magnitude with flow per lane, vehicle length and speed.",
        "A fraction between 0 and 1 is a valid percent value on its own, so the unit error is "
        "only visible against the flow.",
        "Multiply by 100 if the source reports a fraction.",
        TC,
        ("occupancy_pct",),
        "series",
        v009,
        needs=("registry",),
    )
)


def v010(ctx: RuleContext) -> pd.DataFrame:
    n = ctx.config.stuck_run
    return union(
        ctx,
        [
            f"SELECT _row, station_id AS series, 'vehicle_count' AS field, 'identical values "
            f"for ' || run || ' consecutive intervals' AS detail FROM (SELECT _row, station_id, "
            f"count(*) OVER (PARTITION BY station_id, grp, v) AS run, v FROM (SELECT _row, "
            f"station_id, v, row_number() OVER (PARTITION BY station_id ORDER BY ts) - "
            f"row_number() OVER (PARTITION BY station_id, v ORDER BY ts) AS grp FROM (SELECT "
            f"_row, station_id, interval_start__ts AS ts, vehicle_count || '|' || "
            f"mean_speed_kmh || '|' || occupancy_pct AS v FROM {ctx.table} WHERE "
            f"interval_start__ts IS NOT NULL AND vehicle_count__n > 0))) WHERE run >= {n}"
        ],
    )


register(
    Rule(
        "SK-V010",
        "V",
        "No stuck sensor",
        "warning",
        f"A station does not repeat identical count, speed and occupancy for {6} or more "
        "consecutive intervals while traffic is flowing.",
        "Real traffic varies from interval to interval; frozen values mean the detector or the "
        "link stopped updating.",
        "Mark stuck intervals as suspect at the source and repair the detector.",
        TC,
        ("vehicle_count", "mean_speed_kmh", "occupancy_pct"),
        "series",
        v010,
    )
)


def v011(ctx: RuleContext) -> pd.DataFrame:
    return union(
        ctx,
        [
            f"SELECT _row, station_id AS series, 'interval_start' AS field, 'interval does not "
            f"start on a ' || interval_minutes__n || ' minute boundary' AS detail FROM "
            f"{ctx.table} WHERE interval_start__ts IS NOT NULL AND interval_minutes__n > 0 AND "
            f"epoch(interval_start__ts)::BIGINT % (interval_minutes__n::BIGINT * 60) <> 0"
        ],
    )


register(
    Rule(
        "SK-V011",
        "V",
        "Intervals aligned to their length",
        "warning",
        "An interval of n minutes starts at a multiple of n minutes after midnight UTC.",
        "Unaligned starts point to a drifting station clock, which also shifts counts between "
        "intervals.",
        "Synchronise station clocks and floor interval starts to the boundary.",
        TC,
        ("interval_start",),
        "record",
        v011,
        Example("traffic_counts", {"interval_start": "2025-03-03T04:07:12Z"}, {}),
    )
)


def v012(ctx: RuleContext) -> pd.DataFrame:
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, 'road_name_en' AS field, 'English name field holds "
            f"Arabic text' AS detail FROM {ctx.table} WHERE regexp_matches(road_name_en, "
            f"'{ARABIC_LETTERS}')",
            f"SELECT _row, NULL AS series, 'road_name_ar' AS field, 'Arabic name field holds "
            f"no Arabic text' AS detail FROM {ctx.table} WHERE road_name_ar IS NOT NULL AND NOT "
            f"regexp_matches(road_name_ar, '{ARABIC_LETTERS}')",
        ],
    )


register(
    Rule(
        "SK-V012",
        "V",
        "Road name script matches the field",
        "warning",
        "road_name_en holds no Arabic letters and road_name_ar holds Arabic letters.",
        "Mixed scripts break search, sorting and bilingual display.",
        "Fill each name field in its own language.",
        RS,
        ("road_name_en", "road_name_ar"),
        "record",
        v012,
        Example("road_segments", {"road_name_en": "ممر الكثبان"}, {}),
    )
)


def hourly_profiles(ctx: RuleContext, tables: list[str]) -> pd.DataFrame:
    """Share of each station's traffic by UTC hour of day."""
    if not tables:
        return pd.DataFrame()
    unions = " UNION ALL ".join(
        f"SELECT station_id, hour(interval_start__ts) AS h, vehicle_count__n AS n FROM {t} "
        f"WHERE interval_start__ts IS NOT NULL AND vehicle_count__n >= 0"
        for t in tables
    )
    frame = ctx.sql(f"SELECT station_id, h, sum(n) AS n FROM ({unions}) GROUP BY ALL")
    if frame.empty:
        return frame
    wide = frame.pivot_table(index="station_id", columns="h", values="n", aggfunc="sum")
    wide = wide.reindex(columns=range(24)).fillna(0.0)
    totals = wide.sum(axis=1).replace(0, np.nan)
    return wide.div(totals, axis=0).dropna()


def v013(ctx: RuleContext) -> pd.DataFrame:
    tables = [f.table for f in ctx.all_of("traffic_counts")]
    profiles = hourly_profiles(ctx, tables)
    own = ctx.sql(f"SELECT DISTINCT station_id FROM {ctx.table} WHERE station_id IS NOT NULL")
    if profiles.empty or len(profiles) < 5:
        return findings()
    reference = profiles.median(axis=0).to_numpy()
    bad: dict[str, int] = {}
    for station in own["station_id"]:
        if station not in profiles.index:
            continue
        p = profiles.loc[station].to_numpy()
        corr = [float(np.corrcoef(np.roll(p, -lag), reference)[0, 1]) for lag in range(24)]
        best = int(np.nanargmax(corr))
        if best != 0 and corr[best] - corr[0] > ctx.config.profile_min_corr_gain:
            bad[str(station)] = best if best <= 12 else best - 24
    if not bad:
        return findings()
    rows = ctx.sql(
        f"SELECT _row, station_id FROM {ctx.table} WHERE station_id IN {sql_list(sorted(bad))}"
    )
    return findings(
        [
            {
                "_row": int(r),
                "series": s,
                "field": "interval_start",
                "detail": f"daily profile is shifted by {bad[s]:+d} h against the network; "
                + (
                    "consistent with local time labelled as UTC"
                    if bad[s] == 4
                    else "check the station clock and time zone"
                ),
            }
            for r, s in zip(rows["_row"], rows["station_id"], strict=True)
        ]
    )


register(
    Rule(
        "SK-V013",
        "V",
        "Daily profile aligned with the network",
        "warning",
        "A station's traffic by hour of day lines up with the median profile of all stations "
        "in UTC. The median is the reference, so the rule only works while stations with the "
        "same offset are a minority of the network.",
        "Local time (UTC+04:00) written with a Z moves the morning peak four hours later; the "
        "values look valid one by one.",
        "Convert station timestamps from Asia/Dubai to UTC before export.",
        TC,
        ("interval_start",),
        "series",
        v013,
    )
)

__all__ = ["CR", "RS", "TC"]
