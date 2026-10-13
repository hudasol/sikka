"""Quality propagation: capture recapture (Chapman) and unresolved duplicates.

Chapman's estimator of the total number of crashes from two overlapping
producers assumes that the two producers detect crashes independently, that
every crash has the same chance of being detected by a given producer, and that
the population is closed over the window. It breaks when detection is
correlated (for example both producers are more likely to record severe
crashes), which makes the estimate too low, or when matching errors create
false overlaps or hide true ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Chapman:
    group: str
    n1: int
    n2: int
    m: int
    union: int

    @property
    def estimate(self) -> float:
        return (self.n1 + 1) * (self.n2 + 1) / (self.m + 1) - 1

    @property
    def variance(self) -> float:
        n1, n2, m = self.n1, self.n2, self.m
        return (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))

    @property
    def completeness(self) -> float:
        """Share of the estimated total seen by at least one of the two producers."""
        return self.union / self.estimate if self.estimate > 0 else math.nan

    def factor_draws(self, gen: np.random.Generator, size: int) -> np.ndarray:
        """Draws of N / U from a normal approximation, truncated at N = U."""
        if self.union <= 0:
            return np.ones(size)
        n = gen.normal(self.estimate, math.sqrt(max(self.variance, 0.0)), size=size)
        return np.maximum(n, self.union) / self.union

    def as_dict(self) -> dict[str, Any]:
        sd = math.sqrt(max(self.variance, 0.0))
        return {
            "group": self.group,
            "owner_reports": self.n1,
            "partner_reports": self.n2,
            "both": self.m,
            "seen_by_either": self.union,
            "estimated_total": self.estimate,
            "estimated_total_low": self.estimate - 1.96 * sd,
            "estimated_total_high": self.estimate + 1.96 * sd,
            "completeness": self.completeness,
        }


def chapman_by_group(capture: dict[str, dict[str, int]]) -> dict[str, Chapman]:
    out = {}
    for group, c in sorted(capture.items()):
        union = c["owner"] + c["partner"] - c["both"]
        out[group] = Chapman(group, c["owner"], c["partner"], c["both"], union)
    return out
