from __future__ import annotations

import copy
import json
from typing import Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from sikka.core.geo import unproject
from sikka.tasking import (
    DISCLAIMER,
    Candidate,
    DroneProfile,
    TaskingConfig,
    build_mission,
    candidates_from_rows,
    compare_strategies,
    plan_missions,
    random_order,
    to_geojson,
    to_kml,
    to_plan,
    validate_plan,
)


def segment(code: str, index: int, x0_km: float, length_km: float, p: float) -> Candidate:
    xs = np.array([x0_km, x0_km + length_km / 2, x0_km + length_km])
    lon, lat = unproject(xs, np.zeros(3))
    return Candidate(
        segment_id=f"SEG-{code}-{index:03d}",
        corridor=code,
        index=index,
        length_km=length_km,
        p_top_k=p,
        coordinates=[[float(a), float(b)] for a, b in zip(lon, lat, strict=True)],
    )


def corridor() -> list[Candidate]:
    # Ten adjacent 1.5 km segments, then one long 20 km segment that cannot be flown.
    out, x = [], 0.0
    probs = [0.05, 0.5, 0.45, 0.4, 0.02, 0.01, 0.3, 0.6, 0.5, 0.2]
    for i, p in enumerate(probs, 1):
        out.append(segment("AAA", i, x, 1.5, p))
        x += 1.5
    out.append(segment("AAA", 11, x, 20.0, 0.5))
    return out


def test_profile_defaults() -> None:
    profile = DroneProfile()
    assert profile.usable_s == pytest.approx(25 * 60 * 0.8)
    assert profile.vertical_s == pytest.approx(60 / 3 + 60 / 2)


def test_mission_flight_time_and_waypoints() -> None:
    seg = segment("BBB", 1, 0.0, 3.0, 0.5)
    m = build_mission("M01", [seg], TaskingConfig())
    # Three km along the corridor and three km straight back at 12 m/s, plus climb and descent.
    assert m.path_km == pytest.approx(6.0, rel=0.01)
    assert m.flight_s == pytest.approx(6000 / 12 + 50, rel=0.01)
    assert m.feasible
    assert m.metadata["disclaimer"] == DISCLAIMER
    assert all(w[2] == 60.0 for w in m.waypoints)
    assert len(m.waypoints) >= 16


def test_long_segment_is_refused_with_a_reason() -> None:
    planned, refused = plan_missions(corridor(), TaskingConfig(max_missions=5))
    assert "SEG-AAA-011" in {s for m in refused for s in m.segments}
    assert all(not m.feasible and "endurance" in m.reason for m in refused)
    assert all(m.feasible for m in planned)
    assert all(m.flight_s <= DroneProfile().usable_s for m in planned)


def test_value_of_information_groups_adjacent_valuable_segments() -> None:
    planned, _ = plan_missions(corridor(), TaskingConfig(max_missions=1))
    segs = planned[0].segments
    indices = sorted(int(s[-3:]) for s in segs)
    assert indices == list(range(indices[0], indices[-1] + 1))
    assert {"SEG-AAA-002", "SEG-AAA-003"} <= set(segs) or {"SEG-AAA-008", "SEG-AAA-009"} <= set(
        segs
    )


def test_missions_never_reuse_a_segment() -> None:
    planned, _ = plan_missions(corridor(), TaskingConfig(max_missions=4))
    seen: list[str] = [s for m in planned for s in m.segments]
    assert len(seen) == len(set(seen))


def test_ordered_planning_and_random_order_are_deterministic() -> None:
    cands = corridor()
    assert random_order(cands, 3) == random_order(cands, 3)
    assert random_order(cands, 3) != random_order(cands, 4)
    planned, _ = plan_missions(cands, TaskingConfig(max_missions=2), order=["SEG-AAA-005"])
    assert planned[0].segments[0] == "SEG-AAA-005"


def rows_from(cands: list[Candidate]) -> tuple[list[dict[str, Any]], dict[str, list[list[float]]]]:
    rows = [
        {
            "segment_id": c.segment_id,
            "corridor": c.corridor,
            "length_km": c.length_km,
            "p_top_k": c.p_top_k,
            "abstained": "",
            "observed": 10 + i,
        }
        for i, c in enumerate(cands)
    ]
    rows.append(
        {
            "segment_id": "SEG-AAA-099",
            "corridor": "AAA",
            "length_km": 1.0,
            "p_top_k": None,
            "abstained": "no_exposure",
            "observed": 3,
        }
    )
    return rows, {c.segment_id: c.coordinates for c in cands}


def test_compare_strategies_uses_the_same_budget() -> None:
    rows, geometry = rows_from(corridor())
    assert len(candidates_from_rows(rows, geometry)) == 11
    plans = compare_strategies(rows, geometry, TaskingConfig(max_missions=2), seed=1)
    assert set(plans) == {"value_of_information", "random", "greedy_crash_count"}
    for plan in plans.values():
        assert len(plan["missions"]) <= 2
    assert plans["value_of_information"]["value"] >= plans["random"]["value"]


def test_exports_carry_the_disclaimer_and_validate() -> None:
    planned, _ = plan_missions(corridor(), TaskingConfig(max_missions=2))
    geo = to_geojson(planned)
    assert geo["disclaimer"] == DISCLAIMER
    assert all(f["properties"]["disclaimer"] == DISCLAIMER for f in geo["features"])
    kml = to_kml(planned)
    assert kml.startswith('<?xml version="1.0"')
    assert "relativeToGround" in kml
    assert "simulation and review only" in kml
    for m in planned:
        plan = to_plan(m)
        assert validate_plan(plan) == []
        assert plan["sikka"]["disclaimer"] == DISCLAIMER
        json.dumps(plan)


MUTATIONS = [
    lambda p: p.update(fileType="Mission"),
    lambda p: p.update(version=2),
    lambda p: p["mission"]["items"].pop(0),
    lambda p: p["mission"]["items"].pop(),
    lambda p: p["mission"]["items"][1].update(command=999),
    lambda p: p["mission"]["items"][1].update(doJumpId=0),
    lambda p: p["mission"]["items"][1]["params"].pop(),
    lambda p: p["mission"]["items"][1]["params"].__setitem__(4, 123.0),
    lambda p: p["mission"]["items"][1]["params"].__setitem__(6, 500.0),
    lambda p: p["mission"].update(cruiseSpeed=0),
    lambda p: p.pop("geoFence", None),
    lambda p: p["mission"].update(plannedHomePosition=[1, 2]),
]


@given(st.integers(min_value=0, max_value=len(MUTATIONS) - 1), st.integers(0, 20))
def test_validator_rejects_broken_plans(pick: int, item: int) -> None:
    """Property: every single structural defect, wherever it is applied, is reported."""
    planned, _ = plan_missions(corridor(), TaskingConfig(max_missions=1))
    plan = to_plan(planned[0])
    assert validate_plan(plan) == []
    broken = copy.deepcopy(plan)
    items = broken["mission"]["items"]
    waypoint = 1 + item % (len(items) - 2)
    items[1], items[waypoint] = items[waypoint], items[1]
    for i, it in enumerate(items, 1):
        it["doJumpId"] = i
    MUTATIONS[pick](broken)
    assert validate_plan(broken)


def test_validator_handles_non_objects() -> None:
    assert validate_plan([]) == ["plan must be an object"]
    assert "mission must be an object" in validate_plan(
        {
            "fileType": "Plan",
            "version": 1,
            "groundStation": "QGroundControl",
            "geoFence": {"version": 2},
            "rallyPoints": {"version": 2},
        }
    )
