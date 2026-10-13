from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from sikka.contract import FEED_MODELS, ProvenanceHeader
from sikka.contract.feedfile import CSV_HEADER_PREFIX
from sikka.core import Paths
from sikka.synth import (
    CORRIDORS,
    PRODUCERS,
    WorldConfig,
    build_network,
    build_world,
    sample_files,
    to_lonlat,
    to_xy,
    write_world,
)
from sikka.synth.network import SegmentTruth

SMALL = WorldConfig(seed=11, segments_per_corridor=8, target_total_crashes=700.0)


@pytest.fixture(scope="module")
def small_world_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("world")
    write_world(build_world(SMALL), out)
    return out


def test_network_shape_and_bbox() -> None:
    segs = build_network(WorldConfig(seed=5))
    assert len(segs) == 240
    assert {s.corridor.code for s in segs} == {c.code for c in CORRIDORS}
    lengths = [s.length_m for s in segs]
    assert min(lengths) >= 500
    assert max(lengths) <= 12000
    for seg in segs:
        for lon, lat in seg.lonlat:
            assert 22.5 < lat < 26.5
            assert 51.0 < lon < 56.5


def test_projection_round_trip() -> None:
    lon, lat = to_lonlat(12.0, -30.0)
    x, y = to_xy(lon, lat)
    assert x == pytest.approx(12.0, abs=1e-3)
    assert y == pytest.approx(-30.0, abs=1e-3)


def test_point_and_heading_along_segment() -> None:
    seg: SegmentTruth = build_network(SMALL)[0]
    assert seg.point_at(0.0) == pytest.approx(seg.xy[0])
    end = seg.point_at(1.0)
    assert end[0] == pytest.approx(seg.xy[-1][0], abs=0.05)
    hx, hy = seg.heading_at(0.5)
    assert hx**2 + hy**2 == pytest.approx(1.0)


def test_polyline_length_matches_declared_length() -> None:
    import math

    for seg in build_network(SMALL):
        chord = sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(seg.xy, seg.xy[1:], strict=False)
        )
        assert chord * 1000 == pytest.approx(seg.length_m, rel=0.01), seg.segment_id
    segs = build_network(SMALL)
    for a, b in itertools.pairwise(segs):
        if a.corridor == b.corridor:
            assert a.xy[-1] == pytest.approx(b.xy[0], abs=1e-4)


def test_world_has_every_feed_and_plausible_scale() -> None:
    world = build_world(WorldConfig(seed=2))
    names = {f.name for f in world.feeds}
    for p in PRODUCERS:
        assert f"crash_records_{p.producer_id.lower()}" in names
    assert {"road_segments_producer_a", "road_segments_producer_c"} <= names
    assert 2500 < len(world.crashes) < 4500
    assert sum(h.multiplier > 1 for h in world.hazard.values()) == 12
    station_share = len(world.stations) / len(world.segments)
    assert 0.5 < station_share < 0.7
    d = world.feed("crash_records_producer_d")
    assert {r["severity"] for r in d.records} <= {"fatal", "serious_injury"}
    assert all("segment_ref" not in r for r in d.records)


def test_same_seed_gives_identical_bytes(tmp_path: Path, small_world_dir: Path) -> None:
    write_world(build_world(SMALL), tmp_path)
    for path in sorted(small_world_dir.rglob("*")):
        if path.is_file():
            twin = tmp_path / path.relative_to(small_world_dir)
            assert twin.read_bytes() == path.read_bytes(), path.name


def test_different_seed_differs(tmp_path: Path, small_world_dir: Path) -> None:
    other = WorldConfig(seed=12, segments_per_corridor=8, target_total_crashes=700.0)
    write_world(build_world(other), tmp_path)
    name = "feeds/crash_records_producer_b.ndjson"
    assert (tmp_path / name).read_bytes() != (small_world_dir / name).read_bytes()


def _records(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".ndjson":
        lines = text.splitlines()
        return json.loads(lines[0])["sikka_header"], [json.loads(x) for x in lines[1:]]
    if path.suffix == ".geojson":
        doc = json.loads(text)
        recs = [{**f["properties"], "geometry": f["geometry"]} for f in doc["features"]]
        return doc["sikka_header"], recs
    first = text.splitlines()[0]
    assert first.startswith(CSV_HEADER_PREFIX)
    return json.loads(first[len(CSV_HEADER_PREFIX) :]), []


def test_clean_feeds_follow_the_contract(small_world_dir: Path) -> None:
    for path in sorted((small_world_dir / "feeds").iterdir()):
        header, records = _records(path)
        parsed = ProvenanceHeader.model_validate(header)
        assert parsed.synthetic is True
        model = FEED_MODELS[parsed.feed_type]
        for record in records:
            model.model_validate(record)


def test_truth_is_written_beside_not_inside_feeds(small_world_dir: Path) -> None:
    truth = json.loads((small_world_dir / "ground_truth" / "truth.json").read_text("utf-8"))
    assert truth["seed"] == 11
    assert sum(s["blackspot"] for s in truth["segments"]) == 12
    for path in (small_world_dir / "feeds").iterdir():
        text = path.read_text(encoding="utf-8")
        assert "true_id" not in text
        assert "__meta__" not in text
        assert "hazard" not in text


def test_committed_samples_are_fresh() -> None:
    root = Paths().root
    files = sample_files()
    stale = [rel for rel, text in files.items() if (root / rel).read_bytes() != text.encode()]
    assert not stale, f"run `sikka generate`; stale samples: {stale}"
