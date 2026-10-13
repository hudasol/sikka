"""Every rule with a documented example: unit test and property based test."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sikka.conformance import REGISTRY, Rule, example_records
from sikka.contract.models import (
    CollisionType,
    ContributingFactor,
    LightCondition,
    RoadSurface,
    Severity,
    Weather,
)

from .helpers import flagged_rows, run_rules

EXAMPLE_RULES = sorted((r for r in REGISTRY.values() if r.example is not None), key=lambda r: r.id)
RECORD_RULES = [r for r in EXAMPLE_RULES if r.example and not r.example.header]
HEADER_RULES = [r for r in EXAMPLE_RULES if r.example and r.example.header]


def _args(t: Any) -> list[str]:
    from typing import get_args

    return list(get_args(t))


@pytest.mark.parametrize("rule", RECORD_RULES, ids=lambda r: r.id)
def test_failing_example_is_flagged_and_passing_is_not(rule: Rule) -> None:
    assert rule.example is not None
    failing, passing = example_records(rule.example)
    found = run_rules(rule.example.feed_type, [failing, passing], {rule.id})
    assert flagged_rows(found, rule.id) == {1}, found.to_dict("records")


@pytest.mark.parametrize("rule", HEADER_RULES, ids=lambda r: r.id)
def test_failing_header_is_flagged_and_valid_header_is_not(rule: Rule) -> None:
    assert rule.example is not None
    assert rule.example.header is not None
    _, passing = example_records(rule.example)
    bad = run_rules(rule.example.feed_type, [passing], {rule.id}, **rule.example.header)
    good = run_rules(rule.example.feed_type, [passing], {rule.id})
    assert (bad["rule_id"] == rule.id).any()
    assert bad["_row"].isna().all()
    assert not (good["rule_id"] == rule.id).any(), good.to_dict("records")


def _variation(feed_type: str, pinned: set[str]) -> st.SearchStrategy[dict[str, Any]]:
    """Random valid values for fields that the rule example does not touch."""
    if feed_type == "crash_records":
        fields: dict[str, st.SearchStrategy[Any]] = {
            "severity": st.sampled_from(_args(Severity)),
            "collision_type": st.sampled_from(_args(CollisionType)),
            "contributing_factors": st.lists(
                st.sampled_from(_args(ContributingFactor)), max_size=3, unique=True
            ),
            "weather": st.sampled_from(_args(Weather)),
            "light_condition": st.sampled_from(_args(LightCondition)),
            "road_surface": st.sampled_from(_args(RoadSurface)),
            "vehicles_involved": st.integers(min_value=1, max_value=20),
            "direction": st.sampled_from(["forward", "reverse"]),
        }
    elif feed_type == "traffic_counts":
        fields = {
            "quality_flag": st.sampled_from(["ok", "estimated", "suspect"]),
            "vehicle_count": st.integers(min_value=1000, max_value=5000),
        }
    else:
        fields = {
            "lane_count": st.integers(min_value=2, max_value=10),
            "speed_limit_kmh": st.sampled_from([80, 100, 120, 140]),
            "road_class": st.sampled_from(["motorway", "trunk", "primary", "secondary"]),
        }
    return st.fixed_dictionaries({k: v for k, v in fields.items() if k not in pinned})


@pytest.mark.parametrize("rule", RECORD_RULES, ids=lambda r: r.id)
@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_rule_flags_exactly_the_mutated_records(rule: Rule, data: st.DataObject) -> None:
    """Property: among valid random records, the rule flags exactly those carrying its fault."""
    assert rule.example is not None
    feed_type = rule.example.feed_type
    failing, passing = example_records(rule.example)
    pinned = set(rule.example.failing) | set(rule.example.passing)
    majority_rule = rule.id == "SK-X004"
    n = data.draw(st.integers(min_value=3 if majority_rule else 1, max_value=6))
    mutated = data.draw(
        st.sets(st.integers(min_value=1, max_value=n), max_size=1 if majority_rule else n)
    )
    records = []
    for row in range(1, n + 1):
        base = failing if row in mutated else passing
        record = dict(base) | data.draw(_variation(feed_type, pinned))
        if feed_type == "crash_records":
            record["crash_id"] = f"PB-{row:07d}"
        records.append(record)
    found = run_rules(feed_type, records, {rule.id})
    assert flagged_rows(found, rule.id) == mutated
