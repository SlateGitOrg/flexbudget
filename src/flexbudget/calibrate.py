"""Calibrate budget standards against what the prior year's costs imply.

For each variable line, regress clinic-month cost on visits by type with a separate intercept
per clinic (ordinary least squares via `numpy.linalg.lstsq`). The slope for a visit type is the
estimated cost of one visit of that type. A standard that is more than 10% away from the
estimate is reported as a budget problem rather than a clinic problem.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constants import (
    CALIBRATION_TOLERANCE,
    DRIVER_HOURS_PER_VISIT,
    DRIVER_USD_PER_HOUR,
    DRIVER_USD_PER_VISIT,
    VARIABLE_LINES,
    VISIT_TYPES,
)
from .inputs import Inputs

COLUMNS = ["line", "visit_type", "standard", "estimate", "std_error", "gap", "flag"]


@dataclass(frozen=True)
class OlsFit:
    slopes: np.ndarray
    std_errors: np.ndarray
    n_obs: int
    n_params: int


def ols_with_intercepts(y: np.ndarray, x: np.ndarray, groups: np.ndarray) -> OlsFit:
    """OLS of y on x plus one intercept per group; returns the slopes on x with standard errors."""
    labels, codes = np.unique(groups, return_inverse=True)
    dummies = np.zeros((len(y), len(labels)))
    dummies[np.arange(len(y)), codes] = 1.0
    design = np.hstack([x, dummies])
    coef, _res, rank, _sv = np.linalg.lstsq(design, y, rcond=None)
    n_obs, n_params = design.shape
    if rank < n_params:
        raise ValueError("design matrix is rank deficient; visit types are not identifiable")
    residuals = y - design @ coef
    dof = n_obs - n_params
    sigma2 = float(residuals @ residuals) / dof
    cov = sigma2 * np.linalg.inv(design.T @ design)
    k = x.shape[1]
    return OlsFit(coef[:k], np.sqrt(np.diag(cov)[:k]), n_obs, n_params)


def standard_cost_per_visit(standards: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Standard cost of one visit by (line, visit type); labour is hours x standard wage rate."""
    out: dict[tuple[str, str], float] = {}
    per_visit = standards[standards["driver"] == DRIVER_USD_PER_VISIT]
    for row in per_visit.itertuples():
        out[(row.line, row.visit_type)] = float(row.value)
    wage = float(standards.loc[standards["driver"] == DRIVER_USD_PER_HOUR, "value"].iloc[0])
    hours = standards[standards["driver"] == DRIVER_HOURS_PER_VISIT]
    for row in hours.itertuples():
        out[(row.line, row.visit_type)] = float(row.value) * wage
    return out


def prior_year_months(inputs: Inputs) -> list:
    months = sorted(inputs.budget_visits["month"].unique())
    return months[:12]


def calibrate(inputs: Inputs, tolerance: float = CALIBRATION_TOLERANCE) -> pd.DataFrame:
    """Estimate cost per visit type from the first twelve months and compare to the standards."""
    months = prior_year_months(inputs)
    visits = inputs.actual_visits[inputs.actual_visits["month"].isin(months)]
    wide = visits.pivot_table(
        index=["clinic_id", "month"], columns="visit_type", values="visits", aggfunc="sum"
    ).reindex(columns=list(VISIT_TYPES))
    wide = wide.fillna(0.0)
    standards = standard_cost_per_visit(inputs.standards)
    rows = []
    for line in VARIABLE_LINES:
        cost = (
            inputs.actual_cost[
                (inputs.actual_cost["line"] == line) & inputs.actual_cost["month"].isin(months)
            ]
            .set_index(["clinic_id", "month"])["amount"]
            .reindex(wide.index)
        )
        fit = ols_with_intercepts(
            cost.to_numpy(float),
            wide.to_numpy(float),
            wide.index.get_level_values("clinic_id").to_numpy(),
        )
        for i, vt in enumerate(VISIT_TYPES):
            standard = standards[(line, vt)]
            estimate = float(fit.slopes[i])
            gap = (standard - estimate) / estimate
            rows.append(
                {
                    "line": line,
                    "visit_type": vt,
                    "standard": standard,
                    "estimate": estimate,
                    "std_error": float(fit.std_errors[i]),
                    "gap": gap,
                    "flag": abs(gap) > tolerance,
                }
            )
    return pd.DataFrame(rows, columns=COLUMNS)
