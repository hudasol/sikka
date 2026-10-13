"""Small statistical helpers used across layers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class Interval:
    """A point estimate with a lower and upper bound."""

    estimate: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float]:
        return {"estimate": self.estimate, "low": self.low, "high": self.high}


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion.

    With zero trials there is no information, so the interval is the whole of
    [0, 1] and the estimate is reported as NaN by convention of the caller; we
    return 0 with full width to keep JSON finite.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("require 0 <= successes <= trials")
    if trials == 0:
        return Interval(0.0, 0.0, 1.0)
    z = float(stats.norm.ppf(1 - (1 - confidence) / 2))
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half))


def mean_interval(values: Sequence[float], confidence: float = 0.95) -> Interval:
    """Mean with a Student t interval. One value gives a zero width interval."""
    n = len(values)
    if n == 0:
        raise ValueError("need at least one value")
    mean = sum(values) / n
    if n == 1:
        return Interval(mean, mean, mean)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    half = float(stats.t.ppf(1 - (1 - confidence) / 2, n - 1)) * math.sqrt(var / n)
    return Interval(mean, mean - half, mean + half)
