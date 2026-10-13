from __future__ import annotations

from typing import Any, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from sikka.contract import (
    FEED_MODELS,
    VERSIONS,
    ContractModel,
    CrashRecord,
    ProvenanceHeader,
    RoadSegment,
    TrafficCount,
    is_prohibited_field,
    normalise_field_name,
    version_schemas,
)
from sikka.contract.models import CollisionType, ContributingFactor, Severity


def example_record(model: type[ContractModel]) -> dict[str, Any]:
    """Build a record from the examples declared on each field."""
    out: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        assert info.examples, f"{model.__name__}.{name} needs an example"
        out[name] = info.examples[0]
    return out


@pytest.mark.parametrize("model", [ProvenanceHeader, *FEED_MODELS.values()])
def test_examples_are_valid(model: type[ContractModel]) -> None:
    model.model_validate(example_record(model))


@pytest.mark.parametrize("model", [ProvenanceHeader, *FEED_MODELS.values()])
def test_every_field_is_bilingual(model: type[ContractModel]) -> None:
    for name, info in model.model_fields.items():
        assert info.description, name
        extra = info.json_schema_extra
        assert isinstance(extra, dict)
        ar = extra["x-description-ar"]
        assert isinstance(ar, str)
        assert any("؀" <= ch <= "ۿ" for ch in ar), name


def test_nulls_are_refused_absent_is_fine() -> None:
    record = example_record(CrashRecord)
    record["segment_ref"] = None
    with pytest.raises(ValidationError, match="absent, not null"):
        CrashRecord.model_validate(record)
    del record["segment_ref"]
    assert CrashRecord.model_validate(record).segment_ref is None


def test_unknown_fields_are_refused() -> None:
    record = example_record(TrafficCount)
    record["plate_number"] = "X"
    with pytest.raises(ValidationError, match="Extra inputs"):
        TrafficCount.model_validate(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at", "2023-05-14T17:42:00+04:00"),
        ("occurred_at", "1684086120"),
        ("crash_id", "b-2023-1"),
        ("vehicles_involved", 0),
        ("vehicles_involved", 21),
        ("severity", "3"),
        ("lat", 91.0),
    ],
)
def test_crash_constraints(field: str, value: Any) -> None:
    record = example_record(CrashRecord)
    record[field] = value
    with pytest.raises(ValidationError):
        CrashRecord.model_validate(record)


def test_segment_geometry_needs_two_points() -> None:
    record = example_record(RoadSegment)
    record["geometry"] = {"type": "LineString", "coordinates": [[54.4, 24.4]]}
    with pytest.raises(ValidationError):
        RoadSegment.model_validate(record)


@given(
    severity=st.sampled_from(get_args(Severity)),
    collision=st.sampled_from(get_args(CollisionType)),
    factors=st.lists(st.sampled_from(get_args(ContributingFactor)), max_size=8),
    vehicles=st.integers(min_value=1, max_value=20),
    lat=st.floats(min_value=22.5, max_value=26.5),
    lon=st.floats(min_value=51.0, max_value=56.5),
)
def test_any_record_inside_the_domain_validates(
    severity: str, collision: str, factors: list[str], vehicles: int, lat: float, lon: float
) -> None:
    record = example_record(CrashRecord) | {
        "severity": severity,
        "collision_type": collision,
        "contributing_factors": factors,
        "vehicles_involved": vehicles,
        "lat": lat,
        "lon": lon,
    }
    CrashRecord.model_validate(record)


@given(st.text(min_size=1, max_size=50))
def test_identifier_pattern_is_enforced(text: str) -> None:
    record = example_record(CrashRecord) | {"crash_id": text}
    ok = all(ch.isascii() and (ch.isupper() or ch.isdigit() or ch in "_-") for ch in text)
    ok = ok and 3 <= len(text) <= 40
    if ok:
        CrashRecord.model_validate(record)
    else:
        with pytest.raises(ValidationError):
            CrashRecord.model_validate(record)


def test_schemas_have_no_nullable_unions() -> None:
    for version in VERSIONS.values():
        for name, schema in version_schemas(version).items():
            text = str(schema)
            assert "'null'" not in text, name
            assert "$ref" not in text, name
            assert schema["additionalProperties"] is False


def test_optional_fields_are_not_required() -> None:
    schema = version_schemas(VERSIONS["1.0.0"])["crash_records"]
    assert "segment_ref" not in schema["required"]
    assert "crash_id" in schema["required"]


def test_prohibited_field_matching() -> None:
    assert is_prohibited_field("Plate_Number")
    assert is_prohibited_field("emirates-id")
    assert not is_prohibited_field("road_name_en")
    assert normalise_field_name("A_b-C") == "abc"
