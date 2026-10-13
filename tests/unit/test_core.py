from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sikka.core import (
    LOCAL_TZ,
    Paths,
    content_hash,
    find_repo_root,
    format_utc,
    is_utc_z,
    is_valid_id,
    make_id,
    mean_interval,
    parse_utc,
    rng,
    round_floats,
    stable_json_dumps,
    to_local,
    wilson_interval,
)


def test_rng_is_reproducible_per_stream() -> None:
    a = rng(7, "crashes").random(5)
    b = rng(7, "crashes").random(5)
    c = rng(7, "exposure").random(5)
    assert a.tolist() == b.tolist()
    assert a.tolist() != c.tolist()


def test_rng_rejects_negative_seed() -> None:
    with pytest.raises(ValueError, match="non negative"):
        rng(-1)


def test_stable_json_is_sorted_and_compact() -> None:
    assert stable_json_dumps({"b": 1, "a": [1.5, "س"]}) == '{"a":[1.5,"س"],"b":1}'
    assert stable_json_dumps({"b": 1, "a": 2}, indent=2) == '{\n  "a": 2,\n  "b": 1\n}'


def test_round_floats_handles_nesting_and_negative_zero() -> None:
    out = round_floats({"x": [1.23456789, (-0.0000001,)], "y": "z"}, 3)
    assert out == {"x": [1.235, [0.0]], "y": "z"}


def test_time_round_trip() -> None:
    moment = parse_utc("2024-03-01T10:15:00Z")
    assert moment.tzinfo is not None
    assert format_utc(moment) == "2024-03-01T10:15:00Z"
    assert to_local(moment).hour == 14
    assert LOCAL_TZ.utcoffset(None) == timedelta(hours=4)


@pytest.mark.parametrize(
    "text",
    ["2024-03-01T10:15:00", "2024-03-01T10:15:00+04:00", "1709287200", "2024-03-01 10:15:00Z"],
)
def test_parse_utc_rejects_non_z(text: str) -> None:
    assert not is_utc_z(text)
    with pytest.raises(ValueError, match="UTC"):
        parse_utc(text)


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        format_utc(datetime(2024, 1, 1))
    with pytest.raises(ValueError, match="naive"):
        to_local(datetime(2024, 1, 1))


def test_format_utc_converts_offsets() -> None:
    moment = datetime(2024, 1, 1, 4, 0, tzinfo=timezone(timedelta(hours=4)))
    assert format_utc(moment) == "2024-01-01T00:00:00Z"
    assert format_utc(datetime(2024, 1, 1, tzinfo=UTC)) == "2024-01-01T00:00:00Z"


def test_ids() -> None:
    assert is_valid_id("SEG-0001")
    assert not is_valid_id("seg-1")
    assert not is_valid_id("AB")
    ident = make_id("CR", "a", "b")
    assert ident == make_id("CR", "a", "b")
    assert is_valid_id(ident)
    assert len(content_hash(b"x")) == 16
    with pytest.raises(ValueError, match="pattern"):
        make_id("bad prefix", "a")


def test_wilson_known_value() -> None:
    # Reference: 8 of 10 gives roughly [0.490, 0.943] at 95 percent.
    iv = wilson_interval(8, 10)
    assert iv.estimate == pytest.approx(0.8)
    assert iv.low == pytest.approx(0.4902, abs=1e-3)
    assert iv.high == pytest.approx(0.9433, abs=1e-3)
    assert wilson_interval(0, 0).as_dict() == {"estimate": 0.0, "low": 0.0, "high": 1.0}
    with pytest.raises(ValueError, match="successes"):
        wilson_interval(3, 2)


@given(st.integers(min_value=0, max_value=500), st.integers(min_value=0, max_value=500))
def test_wilson_bounds_contain_estimate(a: int, b: int) -> None:
    successes, trials = min(a, b), max(a, b)
    iv = wilson_interval(successes, trials)
    assert 0.0 <= iv.low <= iv.high <= 1.0
    if trials:
        assert iv.low - 1e-12 <= iv.estimate <= iv.high + 1e-12


def test_mean_interval() -> None:
    iv = mean_interval([1.0, 2.0, 3.0])
    assert iv.estimate == pytest.approx(2.0)
    assert iv.low < 2.0 < iv.high
    assert mean_interval([5.0]).as_dict() == {"estimate": 5.0, "low": 5.0, "high": 5.0}
    with pytest.raises(ValueError, match="at least one"):
        mean_interval([])
    assert math.isclose(iv.high - 2.0, 2.0 - iv.low)


def test_repo_root_detection(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    root = find_repo_root()
    assert (root / "pyproject.toml").is_file()
    assert Paths(root).contract == root / "contract"
    monkeypatch.setenv("SIKKA_ROOT", str(root / "docs"))
    assert find_repo_root() == (root / "docs").resolve()
