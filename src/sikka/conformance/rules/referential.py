"""R family: references between records and to the road segment registry."""

from __future__ import annotations

import duckdb
import pandas as pd

from sikka.conformance.context import CELL_KM, RuleContext, point_segment_km, x_km, y_km
from sikka.conformance.registry import Example, Rule, findings, register
from sikka.conformance.rules.structural import union
from sikka.contract import UAE_BBOX
from sikka.ingest import StagedFeed

CR, TC = ("crash_records",), ("traffic_counts",)
B = UAE_BBOX


def build_registry(con: duckdb.DuckDBPyConnection, feeds: list[StagedFeed], buffer_m: float) -> int:
    """Create reg_segments, reg_pieces and reg_cells from every registry feed in the run."""
    registries = [f for f in feeds if f.feed_type == "road_segments"]
    if registries:
        parts = " UNION ALL ".join(
            f"SELECT segment_id, road_name_en, road_name_ar, road_class, length_m__n AS "
            f"length_m, lane_count__n AS lane_count, speed_limit_kmh__n AS speed_limit_kmh, "
            f"owner_producer_id, _raw, '{f.file}' AS file, _row FROM {f.table} WHERE "
            f"segment_id IS NOT NULL"
            for f in registries
        )
        con.execute(
            f"CREATE OR REPLACE TABLE reg_all AS {parts}; "
            "CREATE OR REPLACE TABLE reg_segments AS SELECT * EXCLUDE (_raw, rn) FROM ("
            "SELECT *, row_number() OVER (PARTITION BY segment_id ORDER BY file, _row) AS rn "
            "FROM reg_all) WHERE rn = 1"
        )
        con.execute(
            "CREATE OR REPLACE TABLE reg_coords AS SELECT segment_id, from_json(json_extract("
            "_raw, '$.geometry.coordinates'), '[[\"DOUBLE\"]]') AS c FROM (SELECT * FROM reg_all "
            "WHERE json_type(_raw, '$.geometry.coordinates') = 'ARRAY')"
        )
        con.execute(
            f"CREATE OR REPLACE TABLE reg_pieces AS SELECT segment_id, {x_km('c[i][1]')} AS x0, "
            f"{y_km('c[i][2]')} AS y0, {x_km('c[i + 1][1]')} AS x1, {y_km('c[i + 1][2]')} AS y1 "
            f"FROM (SELECT segment_id, c, unnest(range(1, len(c))) AS i FROM reg_coords) "
            f"WHERE c[i][1] IS NOT NULL AND c[i + 1][1] IS NOT NULL"
        )
    else:
        con.execute(
            "CREATE OR REPLACE TABLE reg_all (segment_id VARCHAR, road_name_en VARCHAR, "
            "road_name_ar VARCHAR, road_class VARCHAR, length_m DOUBLE, lane_count DOUBLE, "
            "speed_limit_kmh DOUBLE, owner_producer_id VARCHAR, _raw VARCHAR, file VARCHAR, "
            "_row INTEGER);"
            "CREATE OR REPLACE TABLE reg_segments AS SELECT * EXCLUDE (_raw) FROM reg_all;"
            "CREATE OR REPLACE TABLE reg_pieces (segment_id VARCHAR, x0 DOUBLE, y0 DOUBLE, "
            "x1 DOUBLE, y1 DOUBLE)"
        )
    pad = buffer_m / 1000.0
    lo = "CAST(floor((least({a}, {b}) - {pad}) / {cell}) AS BIGINT)"
    hi = "CAST(floor((greatest({a}, {b}) + {pad}) / {cell}) AS BIGINT)"
    bounds = ", ".join(
        f"{expr.format(a=a, b=b, pad=pad, cell=CELL_KM)} AS {name}"
        for name, expr, a, b in (
            ("cx0", lo, "x0", "x1"),
            ("cx1", hi, "x0", "x1"),
            ("cy0", lo, "y0", "y1"),
            ("cy1", hi, "y0", "y1"),
        )
    )
    con.execute(
        "CREATE OR REPLACE TABLE reg_cells AS SELECT cx, unnest(range(cy0, cy1 + 1)) AS cy, "
        "segment_id, x0, y0, x1, y1 FROM (SELECT unnest(range(cx0, cx1 + 1)) AS cx, cy0, cy1, "
        f"segment_id, x0, y0, x1, y1 FROM (SELECT *, {bounds} FROM reg_pieces))"
    )
    row = con.execute("SELECT count(*) FROM reg_segments").fetchone()
    return int(row[0]) if row else 0


def _skip(ctx: RuleContext) -> bool:
    return not ctx.has_registry


def r001(ctx: RuleContext) -> pd.DataFrame:
    if _skip(ctx):
        return findings()
    return union(
        ctx,
        [
            f"SELECT t._row, NULL AS series, 'segment_ref' AS field, 'segment ' || "
            f"t.segment_ref || ' is not in the registry' AS detail FROM {ctx.table} t WHERE "
            f"t.segment_ref__t = 'VARCHAR' AND t.segment_ref NOT IN (SELECT segment_id FROM "
            f"reg_segments)"
        ],
    )


register(
    Rule(
        "SK-R001",
        "R",
        "Segment reference exists",
        "error",
        "segment_ref names a segment_id that is present in the road segment registry.",
        "References that do not resolve drop the record from every per segment analysis.",
        "Use the registry identifier exactly, with its prefix and leading zeros.",
        CR + TC,
        ("segment_ref",),
        "record",
        r001,
        Example("crash_records", {"segment_ref": "SEG-DUN-10"}, {}),
        needs=("registry",),
    )
)


def _crash_xy(ctx: RuleContext) -> str:
    return (
        f"SELECT _row, segment_ref, {x_km('lon__n')} AS px, {y_km('lat__n')} AS py FROM "
        f"{ctx.table} WHERE lat__n BETWEEN {B['lat_min']} AND {B['lat_max']} AND lon__n BETWEEN "
        f"{B['lon_min']} AND {B['lon_max']}"
    )


def r002(ctx: RuleContext) -> pd.DataFrame:
    if _skip(ctx):
        return findings()
    buffer_km = ctx.config.buffer_m / 1000.0
    dist = point_segment_km("p.px", "p.py")
    return union(
        ctx,
        [
            f"SELECT p._row, NULL AS series, 'lat' AS field, CASE WHEN d IS NULL THEN 'no "
            f"segment within {ctx.config.buffer_m:g} m' ELSE 'nearest segment is ' || "
            f"CAST(round(d * 1000) AS BIGINT) || ' m away' END AS detail FROM (SELECT p._row, "
            f"min({dist}) AS d FROM ({_crash_xy(ctx)}) p LEFT JOIN reg_cells c ON c.cx = "
            f"CAST(floor(p.px / {CELL_KM}) AS BIGINT) AND c.cy = CAST(floor(p.py / {CELL_KM}) AS "
            f"BIGINT) GROUP BY p._row) p WHERE d IS NULL OR d > {buffer_km}"
        ],
    )


register(
    Rule(
        "SK-R002",
        "R",
        "Crash within a segment buffer",
        "error",
        "A crash location lies within 250 metres of some segment centre line in the registry.",
        "Crashes that cannot be placed on the network cannot be ranked and may belong to "
        "another road owner.",
        "Check the coordinates, or add the missing segment to the registry.",
        CR,
        ("lat", "lon"),
        "record",
        r002,
        Example("crash_records", {"lat": 23.60}, {}),
        needs=("registry",),
    )
)


def r003(ctx: RuleContext) -> pd.DataFrame:
    if _skip(ctx):
        return findings()
    tol_km = ctx.config.ref_tolerance_m / 1000.0
    dist = point_segment_km("p.px", "p.py")
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, 'segment_ref' AS field, 'location is ' || "
            f"CAST(round(d * 1000) AS BIGINT) || ' m from the referenced segment' AS detail FROM "
            f"(SELECT p._row, min({dist}) AS d FROM ({_crash_xy(ctx)}) p JOIN reg_pieces r ON "
            f"r.segment_id = p.segment_ref GROUP BY p._row) WHERE d > {tol_km}"
        ],
    )


register(
    Rule(
        "SK-R003",
        "R",
        "Location agrees with the segment reference",
        "warning",
        "When a crash names a segment, its location is within 500 metres of that segment.",
        "Disagreement means either the reference or the coordinates are wrong, so the crash "
        "may be counted on the wrong segment.",
        "Derive segment_ref from the coordinates, or correct the coordinates.",
        CR,
        ("segment_ref", "lat", "lon"),
        "record",
        r003,
        Example("crash_records", {"segment_ref": "SEG-DUN-030"}, {}),
        needs=("registry",),
    )
)


def r004(ctx: RuleContext) -> pd.DataFrame:
    return union(
        ctx,
        [
            f"SELECT _row, station_id AS series, 'segment_ref' AS field, 'station usually "
            f"reports ' || mode_ref || ', this row says ' || segment_ref AS detail FROM (SELECT "
            f"_row, station_id, segment_ref, mode(segment_ref) OVER (PARTITION BY station_id) AS "
            f"mode_ref FROM {ctx.table} WHERE station_id IS NOT NULL AND segment_ref IS NOT "
            f"NULL) WHERE segment_ref <> mode_ref"
        ],
    )


register(
    Rule(
        "SK-R004",
        "R",
        "Station maps to one segment",
        "warning",
        "Every row of a station names the same segment.",
        "A station that jumps between segments mixes exposure of different roads.",
        "Keep a station to segment table at the source and use it on export.",
        TC,
        ("station_id", "segment_ref"),
        "series",
        r004,
    )
)

__all__ = ["build_registry"]
