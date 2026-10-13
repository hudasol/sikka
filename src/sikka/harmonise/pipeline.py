"""Harmonisation pipeline: conformance findings, adapters, snapping, resolution, exposure."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from sikka.conformance import Source, ValidationResult, run_validation
from sikka.core import format_utc, to_local
from sikka.harmonise.adapters import adapt_count, adapt_crash, new_lineage
from sikka.harmonise.model import (
    SEVERITY_RANK,
    CanonicalCrash,
    Exposure,
    Lineage,
    PairDecision,
    ProducerCrash,
    SourceRef,
    Transformation,
)
from sikka.harmonise.resolution import resolve
from sikka.harmonise.snapping import SegmentIndex
from sikka.harmonise.tables import ADAPTER_VERSION, table_for
from sikka.ingest import open_text

BUFFER_M = 250.0
REF_TOLERANCE_M = 500.0
ARABIC = re.compile(f"[{chr(0x0621)}-{chr(0x064A)}]")


@dataclass
class Segment:
    segment_id: str
    road_name_en: str
    road_name_ar: str
    road_class: str | None
    lane_count: int | None
    speed_limit_kmh: int | None
    length_m: float | None
    owner_producer_id: str | None
    coordinates: list[list[float]]
    lineage: Lineage
    valid_from: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "road_name_en": self.road_name_en,
            "road_name_ar": self.road_name_ar,
            "road_class": self.road_class,
            "lane_count": self.lane_count,
            "speed_limit_kmh": self.speed_limit_kmh,
            "length_m": self.length_m,
            "owner_producer_id": self.owner_producer_id,
            "valid_from": self.valid_from,
        }


@dataclass
class HarmonisedDataset:
    segments: dict[str, Segment]
    producer_crashes: list[ProducerCrash]
    crashes: list[CanonicalCrash]
    decisions: list[PairDecision]
    exposure: dict[str, Exposure]
    periods: dict[str, tuple[str, str]]
    rejected_counts: dict[str, int] = field(default_factory=dict)

    def lineage_index(self) -> dict[str, dict[str, Any]]:
        """Lineage of every canonical record, keyed by canonical id."""
        out: dict[str, dict[str, Any]] = {}
        for crash in self.crashes:
            out[crash.canonical_id] = {
                "canonical_id": crash.canonical_id,
                "kind": "crash",
                "record": {k: v for k, v in crash.as_dict().items() if k != "lineage"},
                "lineage": crash.lineage.as_dict(),
            }
        for exposure in self.exposure.values():
            cid = f"EX-{exposure.segment_id}"
            out[cid] = {
                "canonical_id": cid,
                "kind": "exposure",
                "record": {k: v for k, v in exposure.as_dict().items() if k != "lineage"},
                "lineage": exposure.lineage.as_dict(),
            }
        for segment in self.segments.values():
            cid = f"SG-{segment.segment_id}"
            out[cid] = {
                "canonical_id": cid,
                "kind": "segment",
                "record": segment.as_dict(),
                "lineage": segment.lineage.as_dict(),
            }
        return out

    def resolution_summary(self) -> dict[str, Any]:
        counts = Counter(d.decision for d in self.decisions)
        return {
            "candidate_pairs": len(self.decisions),
            "match": counts.get("match", 0),
            "non_match": counts.get("non_match", 0),
            "unresolved": counts.get("unresolved", 0),
            "producer_records": len(self.producer_crashes),
            "usable_records": sum(1 for c in self.producer_crashes if c.usable),
            "canonical_crashes": len(self.crashes),
        }


def _findings_index(
    result: ValidationResult,
) -> tuple[dict[tuple[str, int], list[dict[str, Any]]], dict[tuple[str, str], set[str]]]:
    rows: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    series: dict[tuple[str, str], set[str]] = defaultdict(set)
    frame = result.all_findings()
    for rule_id, file, row, ser, fld, detail in zip(
        frame["rule_id"],
        frame["file"],
        frame["_row"],
        frame["series"],
        frame["field"],
        frame["detail"],
        strict=True,
    ):
        if not pd.isna(row):
            rows[(file, int(row))].append(
                {
                    "rule_id": rule_id,
                    "field": fld if isinstance(fld, str) else None,
                    "detail": detail,
                }
            )
        if isinstance(ser, str):
            series[(file, ser)].add(rule_id)
    return rows, series


def _read(
    source: Source,
) -> tuple[dict[str, Any] | None, str | None, list[tuple[int, dict[str, Any]]]]:
    stream = source.open()
    try:
        parsed = open_text(source.name, stream)
        records = []
        for n, text in enumerate(parsed.rows, 1):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append((n, value))
        return parsed.header, parsed.feed_type, records
    finally:
        stream.close()


def _segments(
    registry: list[tuple[str, dict[str, Any] | None, list[tuple[int, dict[str, Any]]]]],
) -> dict[str, Segment]:
    rows = [(file, header, n, r) for file, header, recs in registry for n, r in recs]
    en_by_ar: dict[str, Counter[str]] = defaultdict(Counter)
    ar_by_en: dict[str, Counter[str]] = defaultdict(Counter)
    for _, _, _, r in rows:
        en, ar = str(r.get("road_name_en", "")), str(r.get("road_name_ar", ""))
        if en and ar and not ARABIC.search(en) and ARABIC.search(ar):
            en_by_ar[ar][en] += 1
            ar_by_en[en][ar] += 1
    out: dict[str, Segment] = {}
    for file, header, n, r in rows:
        sid = r.get("segment_id")
        if not isinstance(sid, str) or sid in out:
            continue
        producer = (header or {}).get("producer_id")
        lineage = new_lineage(producer if isinstance(producer, str) else None, file, n, sid)
        en, ar = str(r.get("road_name_en", "")), str(r.get("road_name_ar", ""))
        if ARABIC.search(en) and ar in en_by_ar:
            fixed = en_by_ar[ar].most_common(1)[0][0]
            lineage.transformations.append(
                Transformation("road_name_script", "road_name_en", en, fixed, "usual English name")
            )
            en = fixed
        if not ARABIC.search(ar) and en in ar_by_en:
            fixed = ar_by_en[en].most_common(1)[0][0]
            lineage.transformations.append(
                Transformation("road_name_script", "road_name_ar", ar, fixed, "usual Arabic name")
            )
            ar = fixed
        lineage.status = "repaired" if lineage.transformations else "accepted"
        geometry = r.get("geometry") if isinstance(r.get("geometry"), dict) else {}
        coords = geometry.get("coordinates") if isinstance(geometry, dict) else None

        lanes, limit = _num(r, "lane_count"), _num(r, "speed_limit_kmh")
        out[sid] = Segment(
            segment_id=sid,
            road_name_en=en,
            road_name_ar=ar,
            road_class=r.get("road_class") if isinstance(r.get("road_class"), str) else None,
            lane_count=int(lanes) if lanes is not None else None,
            speed_limit_kmh=int(limit) if limit is not None else None,
            length_m=_num(r, "length_m"),
            owner_producer_id=r.get("owner_producer_id")
            if isinstance(r.get("owner_producer_id"), str)
            else None,
            coordinates=coords if isinstance(coords, list) else [],
            lineage=lineage,
            valid_from=r.get("valid_from") if isinstance(r.get("valid_from"), str) else None,
        )
    return out


def _num(record: dict[str, Any], key: str) -> float | None:
    value = record.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _canonical_id(keys: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(keys)).encode("utf-8")).hexdigest()[:12].upper()
    return f"CC-{digest}"


def _canonical(cluster: list[ProducerCrash]) -> CanonicalCrash:
    ordered = sorted(cluster, key=lambda c: (table_for(c.producer_id).resolution_priority, c.key))
    lead = ordered[0]
    severity = lead.severity
    authority = [c for c in ordered if table_for(c.producer_id).severity_authority and c.severity]
    lineage = Lineage(
        sources=[s for c in ordered for s in c.lineage.sources],
        adapter="resolution",
        adapter_version=ADAPTER_VERSION,
        transformations=[t for c in ordered for t in c.lineage.transformations],
        findings=[f for c in ordered for f in c.lineage.findings],
        status="repaired" if any(c.lineage.status == "repaired" for c in ordered) else "accepted",
        merged_from=[c.key for c in ordered] if len(ordered) > 1 else [],
        notes=[n for c in ordered for n in c.lineage.notes],
    )
    if authority and authority[0].severity != severity:
        lineage.transformations.append(
            Transformation(
                "severity_authority",
                "severity",
                severity,
                authority[0].severity,
                f"{authority[0].producer_id} is the authority on injury severity",
            )
        )
        severity = authority[0].severity
    segment = lead.segment_id or next((c.segment_id for c in ordered if c.segment_id), None)
    assert lead.occurred_ts is not None
    assert lead.lat is not None
    assert lead.lon is not None
    occurred = datetime.fromtimestamp(lead.occurred_ts, tz=UTC)
    return CanonicalCrash(
        canonical_id=_canonical_id([c.key for c in ordered]),
        occurred_at=format_utc(occurred),
        lat=round(lead.lat, 6),
        lon=round(lead.lon, 6),
        segment_id=segment,
        severity=severity,
        vehicles=lead.vehicles,
        producers=sorted({c.producer_id for c in ordered}),
        attributes=dict(lead.attributes) | {"local_year": to_local(occurred).year},
        lineage=lineage,
    )


def harmonise(sources: list[Source], references: list[Source] | None = None) -> HarmonisedDataset:
    """Run conformance on ``sources`` and turn them into the canonical model."""
    result = run_validation(sources, references or [])
    try:
        row_findings, series_rules = _findings_index(result)
    finally:
        result.close()
    feeds = []
    for source in sources + (references or []):
        header, feed_type, records = _read(source)
        feeds.append((source.name, header, feed_type, records))

    registry = [(f, h, r) for f, h, t, r in feeds if t == "road_segments"]
    segments = _segments(registry)
    index = SegmentIndex.build({k: s.coordinates for k, s in segments.items()})

    producer_crashes: list[ProducerCrash] = []
    periods: dict[str, tuple[str, str]] = {}
    rejected: Counter[str] = Counter()
    for file, header, feed_type, records in feeds:
        if feed_type != "crash_records":
            continue
        producer = (header or {}).get("producer_id")
        producer = producer if isinstance(producer, str) else None
        if header and isinstance(header.get("period_start"), str):
            periods[file] = (str(header["period_start"]), str(header.get("period_end", "")))
        batch: list[tuple[dict[str, Any], Lineage, int]] = []
        for row, raw in records:
            adapted, lineage = adapt_crash(
                raw,
                producer=producer,
                file=file,
                row=row,
                findings=row_findings.get((file, row), []),
            )
            batch.append((adapted, lineage, row))
        located = [b for b in batch if b[0]["lat"] is not None and b[0]["lon"] is not None]
        lons = np.asarray([b[0]["lon"] for b in located], dtype=np.float64)
        lats = np.asarray([b[0]["lat"] for b in located], dtype=np.float64)
        nearest, dist = index.nearest(lons, lats)
        snapped = {id(b[1]): (nearest[k], float(dist[k])) for k, b in enumerate(located)}
        for adapted, lineage, row in batch:
            seg_id, d = snapped.get(id(lineage), (None, float("inf")))
            ref = adapted["segment_ref"]
            chosen = None
            if ref and ref in segments and adapted["lat"] is not None:
                ref_d = index.distance_to(adapted["lon"], adapted["lat"], ref)
                if ref_d is not None and ref_d <= REF_TOLERANCE_M:
                    chosen, d = ref, ref_d
            if chosen is None and seg_id is not None and d <= BUFFER_M:
                chosen = seg_id
                lineage.transformations.append(
                    Transformation(
                        "snap_to_segment",
                        "segment_id",
                        ref,
                        seg_id,
                        f"nearest centre line, {d:.0f} m",
                    )
                )
            if chosen is None and lineage.status != "rejected":
                lineage.notes.append("no segment within the buffer; not counted on any segment")
            if lineage.status == "rejected":
                rejected[producer or "UNKNOWN"] += 1
            occurred = adapted["occurred"]
            producer_crashes.append(
                ProducerCrash(
                    key=f"{file}#{row}",
                    producer_id=producer or "UNKNOWN",
                    occurred_ts=occurred.timestamp() if occurred else None,
                    lat=adapted["lat"],
                    lon=adapted["lon"],
                    segment_id=chosen,
                    snap_distance_m=round(d, 1) if chosen else None,
                    severity=adapted["severity"],
                    vehicles=adapted["vehicles"],
                    attributes={
                        k: adapted[k]
                        for k in (
                            "collision_type",
                            "contributing_factors",
                            "weather",
                            "light_condition",
                            "road_surface",
                            "direction",
                        )
                        if adapted.get(k) is not None
                    },
                    lineage=lineage,
                )
            )

    decisions, clusters = resolve(producer_crashes)
    by_key = {c.key: c for c in producer_crashes}
    canonical = [_canonical([producer_crashes[k] for k in cluster]) for cluster in clusters]
    canonical.sort(key=lambda c: (c.occurred_at, c.canonical_id))
    owner = {
        key: c.canonical_id
        for c in canonical
        for key in ([s.file + "#" + str(s.row) for s in c.lineage.sources])
    }
    for pair in decisions:
        if pair.decision == "unresolved" and pair.a in owner and pair.b in owner:
            ca, cb = owner[pair.a], owner[pair.b]
            if ca != cb:
                for c in canonical:
                    if c.canonical_id == ca and cb not in c.unresolved_with:
                        c.unresolved_with.append(cb)
                    if c.canonical_id == cb and ca not in c.unresolved_with:
                        c.unresolved_with.append(ca)
    del by_key

    exposure = _exposure(feeds, row_findings, series_rules, segments)
    return HarmonisedDataset(
        segments=segments,
        producer_crashes=producer_crashes,
        crashes=canonical,
        decisions=decisions,
        exposure=exposure,
        periods=periods,
        rejected_counts=dict(rejected),
    )


def _exposure(
    feeds: list[tuple[str, dict[str, Any] | None, str | None, list[tuple[int, dict[str, Any]]]]],
    row_findings: dict[tuple[str, int], list[dict[str, Any]]],
    series_rules: dict[tuple[str, str], set[str]],
    segments: dict[str, Segment],
) -> dict[str, Exposure]:
    per_station: dict[str, dict[str, Any]] = {}
    for file, header, feed_type, records in feeds:
        if feed_type != "traffic_counts":
            continue
        producer = (header or {}).get("producer_id")
        period = (header or {}).get("period_start"), (header or {}).get("period_end")
        for row, raw in records:
            station = raw.get("station_id")
            if not isinstance(station, str):
                continue
            rules = {f["rule_id"] for f in row_findings.get((file, row), [])}
            adapted, reason, repairs = adapt_count(
                raw, rule_ids=rules | series_rules.get((file, station), set())
            )
            entry = per_station.setdefault(
                station,
                {
                    "file": file,
                    "producer": producer,
                    "period": period,
                    "rows": 0,
                    "intervals": {},
                    "refs": Counter(),
                    "rejected": Counter(),
                    "repairs": Counter(),
                },
            )
            entry["rows"] += 1
            ref = raw.get("segment_ref")
            if isinstance(ref, str):
                entry["refs"][ref] += 1
            for r in repairs:
                entry["repairs"][r] += 1
            if adapted is None:
                entry["rejected"][reason or "rejected"] += 1
                continue
            entry["intervals"].setdefault(adapted["start"], adapted)
    by_segment: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for station, entry in sorted(per_station.items()):
        if not entry["refs"]:
            continue
        segment = entry["refs"].most_common(1)[0][0]
        by_segment[segment].append((station, entry))
    out: dict[str, Exposure] = {}
    for segment, stations in sorted(by_segment.items()):
        station, entry = stations[0]
        lineage = Lineage(
            sources=[SourceRef(str(e["producer"]), e["file"], 0, s) for s, e in stations],
            adapter=table_for(str(entry["producer"])).adapter_id,
            adapter_version=ADAPTER_VERSION,
        )
        intervals = list(entry["intervals"].values())
        start, end = entry["period"]
        expected = 0
        if isinstance(start, str) and isinstance(end, str):
            try:
                span = datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                )
                expected = int(span.total_seconds() // 3600)
            except ValueError:
                expected = 0
        for name, n in sorted(entry["repairs"].items()):
            lineage.transformations.append(
                Transformation(name, "station rows", f"{n} rows", "", "applied per interval")
            )
        for reason, n in sorted(entry["rejected"].items()):
            lineage.notes.append(f"{n} intervals rejected: {reason}")
        if len(entry["refs"]) > 1:
            lineage.notes.append("station named more than one segment; the usual one is used")
        aadt = None
        if intervals:
            per_minute = sum(i["count"] for i in intervals) / sum(i["minutes"] for i in intervals)
            aadt = per_minute * 1440.0
            lineage.notes.append(
                f"daily traffic estimated from {len(intervals)} valid intervals "
                "as mean flow per minute times 1440"
            )
        lineage.status = "repaired" if lineage.transformations or entry["rejected"] else "accepted"
        if segment not in segments:
            lineage.notes.append("segment not in the registry")
        out[segment] = Exposure(
            segment_id=segment,
            aadt=round(aadt, 1) if aadt is not None else None,
            stations=[s for s, _ in stations],
            valid_intervals=len(intervals),
            expected_intervals=expected or len(intervals),
            lineage=lineage,
        )
    return out


def severity_max(values: list[str | None]) -> str | None:
    known = [v for v in values if v]
    return max(known, key=lambda v: SEVERITY_RANK[v]) if known else None
