"""Safety performance function: NB2 regression of crash counts on exposure and design."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from statsmodels.discrete.discrete_model import NegativeBinomial
from statsmodels.tools.sm_exceptions import ConvergenceWarning

CLASSES = ("motorway", "trunk", "primary", "secondary")


def design_matrix(df: pd.DataFrame) -> tuple[NDArray[np.float64], list[str]]:
    """Columns: intercept, log AADT, log length, class indicators (motorway is the base), lanes."""
    cols = {
        "intercept": np.ones(len(df)),
        "log_aadt": np.log(df["aadt"].astype(float).to_numpy()),
        "log_length_km": np.log(df["length_km"].astype(float).to_numpy()),
    }
    present = set(df["road_class"])
    for cls in CLASSES[1:]:
        if cls in present:
            cols[f"class_{cls}"] = (df["road_class"] == cls).astype(float).to_numpy()
    if df["lane_count"].nunique() > 1:
        cols["lanes"] = df["lane_count"].astype(float).to_numpy()
    names = list(cols)
    return np.column_stack([cols[n] for n in names]), names


@dataclass
class SpfFit:
    names: list[str]
    coef: NDArray[np.float64]
    cov: NDArray[np.float64]
    alpha: float
    loglik: float
    loglik_null: float
    aic: float
    n: int
    pearson_dispersion: float
    converged: bool

    @property
    def k(self) -> float:
        """Inverse overdispersion (the gamma shape in the Empirical Bayes weight)."""
        return 1.0 / self.alpha if self.alpha > 0 else math.inf

    @property
    def pseudo_r2(self) -> float:
        return 1.0 - self.loglik / self.loglik_null if self.loglik_null else math.nan

    def predict_per_year(
        self, df: pd.DataFrame, coef: NDArray[np.float64] | None = None
    ) -> NDArray[np.float64]:
        x, names = design_matrix(df)
        beta = self.coef if coef is None else coef
        aligned = np.zeros(len(names))
        for i, name in enumerate(names):
            if name in self.names:
                aligned[i] = beta[self.names.index(name)]
        return np.asarray(np.exp(x @ aligned), dtype=np.float64)

    def as_dict(self) -> dict[str, Any]:
        se = np.sqrt(np.clip(np.diag(self.cov), 0, None))
        return {
            "coefficients": [
                {"name": n, "estimate": float(b), "std_error": float(s)}
                for n, b, s in zip(self.names, self.coef, se, strict=True)
            ],
            "alpha": self.alpha,
            "k": self.k,
            "log_likelihood": self.loglik,
            "log_likelihood_null": self.loglik_null,
            "aic": self.aic,
            "pseudo_r2_mcfadden": self.pseudo_r2,
            "pearson_dispersion": self.pearson_dispersion,
            "n_segments": self.n,
            "converged": self.converged,
        }


def fit_spf(df: pd.DataFrame) -> SpfFit:
    """Fit NB2 with log(window years) as offset. ``df`` holds only rankable segments."""
    x, names = design_matrix(df)
    y = df["observed"].astype(float).to_numpy()
    offset = np.log(df["window_years"].astype(float).to_numpy())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        model = NegativeBinomial(y, x, loglike_method="nb2", offset=offset)
        result = model.fit(disp=0, maxiter=500, method="bfgs")
        null = NegativeBinomial(y, np.ones((len(y), 1)), loglike_method="nb2", offset=offset)
        null_result = null.fit(disp=0, maxiter=500, method="bfgs")
    params = np.asarray(result.params, dtype=np.float64)
    cov_full = np.asarray(result.cov_params(), dtype=np.float64)
    beta, alpha = params[:-1], float(params[-1])
    mu = np.exp(x @ beta + offset)
    pearson = float(np.sum((y - mu) ** 2 / (mu + alpha * mu**2)) / max(1, len(y) - len(beta) - 1))
    return SpfFit(
        names=names,
        coef=beta,
        cov=cov_full[:-1, :-1],
        alpha=max(alpha, 1e-6),
        loglik=float(result.llf),
        loglik_null=float(null_result.llf),
        aic=float(result.aic),
        n=len(y),
        pearson_dispersion=pearson,
        converged=bool(result.mle_retvals.get("converged", True)),
    )
