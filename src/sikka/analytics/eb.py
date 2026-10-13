"""Empirical Bayes (Hauer) and the potential for safety improvement."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


@dataclass(frozen=True)
class EbResult:
    weight: Array
    expected: Array
    psi_per_year: Array


def empirical_bayes(predicted: Array, observed: Array, k: float, years: Array) -> EbResult:
    """EB = w P + (1 - w) O with w = 1 / (1 + P / k), P and O over the whole window.

    ``predicted`` is the SPF prediction over the window (per year times years). PSI is
    returned per year: (EB - P) / years.
    """
    p = np.asarray(predicted, dtype=np.float64)
    o = np.asarray(observed, dtype=np.float64)
    w = 1.0 / (1.0 + p / k)
    eb = w * p + (1.0 - w) * o
    return EbResult(
        weight=w, expected=eb, psi_per_year=(eb - p) / np.asarray(years, dtype=np.float64)
    )


def posterior_draws(
    predicted: Array, observed: Array, k: float, gen: np.random.Generator, size: int
) -> Array:
    """Draws of the long run count over the window: Gamma(k + O, scale P / (k + P)).

    Rows are draws, columns are segments. ``predicted`` may itself be a matrix of draws.
    """
    p = np.asarray(predicted, dtype=np.float64)
    o = np.asarray(observed, dtype=np.float64)
    shape = np.broadcast_to(k + o, (size, o.shape[-1]))
    scale = np.broadcast_to(p / (k + p), (size, o.shape[-1]))
    return np.asarray(gen.gamma(shape, scale), dtype=np.float64)
