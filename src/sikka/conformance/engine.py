"""The rule engine: stage feeds, build the registry, run every applicable rule."""

from __future__ import annotations

import io
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

import sikka.conformance.rules  # noqa: F401  (registers the rules)
from sikka.conformance.context import RuleConfig, RuleContext
from sikka.conformance.fields import RECORD_KEY
from sikka.conformance.registry import REGISTRY, Rule, findings, rules_for
from sikka.conformance.rules.referential import build_registry
from sikka.ingest import StagedFeed, open_text, profile_feed, stage

Opener = Callable[[], io.TextIOBase]


@dataclass(frozen=True)
class Source:
    """A feed to read: a display name and a function that opens it as text."""

    name: str
    open: Opener

    @staticmethod
    def from_path(path: Path) -> Source:
        return Source(path.name, lambda: path.open("r", encoding="utf-8-sig", newline=""))

    @staticmethod
    def from_bytes(name: str, data: bytes) -> Source:
        return Source(
            name,
            lambda: io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline=""),
        )


@dataclass
class RuleOutcome:
    rule: Rule
    file: str
    status: str  # "evaluated", "not_applicable" or "skipped"
    findings: pd.DataFrame
    note: str = ""


@dataclass
class ValidationResult:
    feeds: list[StagedFeed]
    outcomes: list[RuleOutcome]
    profiles: dict[str, dict[str, Any]]
    record_keys: dict[str, pd.DataFrame]
    seconds: float
    con: duckdb.DuckDBPyConnection = field(repr=False)
    registry_segments: int = 0

    def validated(self) -> list[StagedFeed]:
        return [f for f in self.feeds if not f.is_reference]

    def quarantined(self, file: str) -> set[int]:
        rows: set[int] = set()
        for o in self.outcomes:
            if o.file == file and o.rule.family == "P" and not o.findings.empty:
                rows.update(int(r) for r in o.findings["_row"].dropna())
        return rows

    def all_findings(self) -> pd.DataFrame:
        frames = []
        for o in self.outcomes:
            if o.findings.empty:
                continue
            frame = o.findings.copy()
            frame.insert(0, "file", o.file)
            frame.insert(0, "rule_id", o.rule.id)
            frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=["rule_id", "file", "_row", "series", "field", "detail"])
        return pd.concat(frames, ignore_index=True)

    def close(self) -> None:
        self.con.close()


DUCKDB_MEMORY_LIMIT = "2GB"
DUCKDB_THREADS = 4


def connect() -> duckdb.DuckDBPyConnection:
    """In memory DuckDB with a bounded memory budget that spills to a temp folder."""
    spill = Path(tempfile.gettempdir()) / "sikka-duckdb"
    spill.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(
        config={
            "memory_limit": DUCKDB_MEMORY_LIMIT,
            "threads": DUCKDB_THREADS,
            "temp_directory": str(spill),
        }
    )


def _missing_context(rule: Rule, ctx: RuleContext) -> str | None:
    if "registry" in rule.needs and not ctx.has_registry:
        return "no road segment registry in the run"
    if "other crash feeds" in rule.needs:
        mine = ctx.feed.producer_id
        if not [f for f in ctx.others("crash_records") if f.producer_id != mine]:
            return "no crash feed from another producer in the run"
    if "traffic counts" in rule.needs and not ctx.all_of("traffic_counts"):
        return "no traffic count feed in the run"
    return None


def _record_keys(con: duckdb.DuckDBPyConnection, feed: StagedFeed) -> pd.DataFrame:
    key = RECORD_KEY.get(feed.feed_type or "")
    if key is None:
        return pd.DataFrame(columns=["_row", "record_id", "lat", "lon"])
    expr = f'"{key}"'
    if feed.feed_type == "traffic_counts":
        expr = "coalesce(station_id, '?') || ' @ ' || coalesce(interval_start, '?')"
    coords = (
        "lat__n AS lat, lon__n AS lon"
        if feed.feed_type == "crash_records"
        else ("NULL AS lat, NULL AS lon")
    )
    return con.execute(f"SELECT _row, {expr} AS record_id, {coords} FROM {feed.table}").df()


def run_validation(
    sources: list[Source],
    references: list[Source] | None = None,
    config: RuleConfig | None = None,
    rule_ids: set[str] | None = None,
) -> ValidationResult:
    """Validate ``sources``; ``references`` give context (registry, other producers) only."""
    started = time.perf_counter()
    config = config or RuleConfig()
    con = connect()
    feeds: list[StagedFeed] = []
    for i, (source, is_ref) in enumerate(
        [(s, False) for s in sources] + [(s, True) for s in references or []]
    ):
        stream = source.open()
        try:
            parsed = open_text(source.name, stream)
            feeds.append(stage(con, parsed, f"feed_{i}", is_reference=is_ref))
        finally:
            stream.close()
    registry_segments = build_registry(con, feeds, config.buffer_m)
    outcomes: list[RuleOutcome] = []
    profiles: dict[str, dict[str, Any]] = {}
    keys: dict[str, pd.DataFrame] = {}
    for feed in feeds:
        if feed.is_reference:
            continue
        profiles[feed.file] = profile_feed(con, feed)
        keys[feed.file] = _record_keys(con, feed)
        ctx = RuleContext(con, feed, feeds, config, has_registry=registry_segments > 0)
        for rule in sorted(REGISTRY.values(), key=lambda r: r.id):
            if rule_ids is not None and rule.id not in rule_ids:
                continue
            applicable = feed.feed_type is not None and rule in rules_for(feed.feed_type)
            if not applicable:
                if feed.feed_type is None and rule.scope == "file" and rule.family == "S":
                    applicable = True
                else:
                    outcomes.append(RuleOutcome(rule, feed.file, "not_applicable", findings()))
                    continue
            missing = _missing_context(rule, ctx)
            if missing:
                outcomes.append(RuleOutcome(rule, feed.file, "skipped", findings(), missing))
                continue
            frame = rule.check(ctx)
            outcomes.append(RuleOutcome(rule, feed.file, "evaluated", frame))
    return ValidationResult(
        feeds=feeds,
        outcomes=outcomes,
        profiles=profiles,
        record_keys=keys,
        seconds=time.perf_counter() - started,
        con=con,
        registry_segments=registry_segments,
    )
