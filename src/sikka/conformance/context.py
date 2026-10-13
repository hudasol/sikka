"""What a rule can see: the DuckDB connection, the feed under test and the run."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import duckdb
import pandas as pd

from sikka.ingest import StagedFeed

# Local equirectangular projection for distances, centred on the network area.
PROJ_LAT0 = 24.3
PROJ_LON0 = 54.3
KM_LAT = 110.574
KM_LON = 111.320 * math.cos(math.radians(PROJ_LAT0))
CELL_KM = 1.0


def x_km(lon: str) -> str:
    return f"(({lon}) - {PROJ_LON0}) * {KM_LON}"


def y_km(lat: str) -> str:
    return f"(({lat}) - {PROJ_LAT0}) * {KM_LAT}"


def point_segment_km(px: str, py: str) -> str:
    """SQL distance in km from (px, py) to the piece (x0, y0)-(x1, y1)."""
    dx, dy = "(x1 - x0)", "(y1 - y0)"
    t = (
        f"GREATEST(0, LEAST(1, CASE WHEN {dx}*{dx} + {dy}*{dy} = 0 THEN 0 ELSE "
        f"((({px}) - x0)*{dx} + (({py}) - y0)*{dy}) / ({dx}*{dx} + {dy}*{dy}) END))"
    )
    return f"sqrt(power(({px}) - (x0 + {t}*{dx}), 2) + power(({py}) - (y0 + {t}*{dy}), 2))"


@dataclass(frozen=True)
class RuleConfig:
    """Thresholds used by the rules. Each one is documented in RULES.md."""

    buffer_m: float = 250.0
    ref_tolerance_m: float = 500.0
    late_days: float = 30.0
    stuck_run: int = 6
    duplicate_minutes: float = 20.0
    duplicate_metres: float = 200.0
    within_feed_minutes: float = 5.0
    within_feed_metres: float = 50.0
    offset_hours: float = 4.0
    offset_tolerance_minutes: float = 20.0
    speed_ratio_max: float = 1.6
    speed_absolute_max: float = 200.0
    ms_speed_ratio: float = 0.5
    ms_occupancy_max: float = 15.0
    fraction_ratio_max: float = 0.05
    exposure_rate_factor: float = 20.0
    zero_month_p: float = 0.001
    profile_min_corr_gain: float = 0.2


@dataclass
class RuleContext:
    con: duckdb.DuckDBPyConnection
    feed: StagedFeed
    feeds: list[StagedFeed]
    config: RuleConfig = field(default_factory=RuleConfig)
    has_registry: bool = False

    @property
    def table(self) -> str:
        return self.feed.table

    def sql(self, query: str) -> pd.DataFrame:
        return self.con.execute(query).df()

    def others(self, feed_type: str) -> list[StagedFeed]:
        """Other feeds of a type in the run, references included."""
        return [f for f in self.feeds if f.feed_type == feed_type and f.key != self.feed.key]

    def all_of(self, feed_type: str) -> list[StagedFeed]:
        return [f for f in self.feeds if f.feed_type == feed_type]
