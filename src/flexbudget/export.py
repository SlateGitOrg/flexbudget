"""Write the star schema CSVs that the Power BI semantic model loads."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .calibrate import standard_cost_per_visit
from .constants import (
    ALL_LINES,
    DRIVER_HOURS_PER_VISIT,
    DRIVER_USD_PER_HOUR,
    FIXED_LINES,
    LINE_LABELS,
    VISIT_TYPE_LABELS,
    VISIT_TYPES,
)
from .dates import label
from .engine import run_engine
from .inputs import Inputs
from .starschema import TABLES, header

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
CLINIC_TYPE_LABELS = {"primary": "Primary care", "urgent_care": "Urgent care"}


def _iso(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")


def build_star(inputs: Inputs, variance: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Return the nine star-schema tables as DataFrames, columns in `starschema` order."""
    variance = run_engine(inputs) if variance is None else variance

    hours = inputs.actual_hours.rename(columns={"hours": "ActualHours"})
    cost = inputs.actual_cost.merge(hours, on=["clinic_id", "month"], how="left")
    cost.loc[cost["line"] != "clinical_labour", "ActualHours"] = pd.NA
    fact_cost = pd.DataFrame(
        {
            "ClinicId": cost["clinic_id"],
            "Date": _iso(cost["month"]),
            "CostLine": cost["line"],
            "ActualCost": cost["amount"],
            "ActualHours": cost["ActualHours"],
        }
    )

    visits = inputs.actual_visits
    fact_visits = pd.DataFrame(
        {
            "ClinicId": visits["clinic_id"],
            "Date": _iso(visits["month"]),
            "VisitType": visits["visit_type"],
            "ActualVisits": visits["visits"].astype(int),
        }
    )

    budget = inputs.budget_visits
    visit_rows = pd.DataFrame(
        {
            "ClinicId": budget["clinic_id"],
            "Date": _iso(budget["month"]),
            "CostLine": "",
            "VisitType": budget["visit_type"],
            "BudgetVisits": budget["visits"].astype(int),
            "FixedBudget": 0.0,
        }
    )
    fixed = inputs.fixed_budget
    fixed_rows = pd.DataFrame(
        {
            "ClinicId": fixed["clinic_id"],
            "Date": _iso(fixed["month"]),
            "CostLine": fixed["line"],
            "VisitType": "",
            "BudgetVisits": 0,
            "FixedBudget": fixed["amount"],
        }
    )
    fact_budget = pd.concat([visit_rows, fixed_rows], ignore_index=True)

    unit = standard_cost_per_visit(inputs.standards)
    wage = float(
        inputs.standards.loc[inputs.standards["driver"] == DRIVER_USD_PER_HOUR, "value"].iloc[0]
    )
    hours_std = inputs.standards[inputs.standards["driver"] == DRIVER_HOURS_PER_VISIT]
    std_hours = {(r.line, r.visit_type): r.value for r in hours_std.itertuples()}
    std_rows = []
    for (line, visit_type), value in sorted(unit.items()):
        labour = line == "clinical_labour"
        std_rows.append(
            {
                "CostLine": line,
                "VisitType": visit_type,
                "UnitCost": round(value, 4),
                "StdHours": std_hours[(line, visit_type)] if labour else pd.NA,
                "StdWageRate": wage if labour else pd.NA,
            }
        )
    standards = pd.DataFrame(std_rows)

    fact_variance = pd.DataFrame(
        {
            "ClinicId": variance["clinic_id"],
            "Date": _iso(variance["month"]),
            "CostLine": variance["line"],
            "StaticBudget": variance["static_budget"],
            "FlexedBudget": variance["flexed_budget"],
            "FlexedBudgetActualMix": variance["flexed_budget_actual_mix"],
            "ActualCost": variance["actual_cost"],
            "VolumeVariance": variance["volume_variance"],
            "MixVariance": variance["mix_variance"],
            "SpendingVariance": variance["spending_variance"],
            "WageRateVariance": variance["wage_rate_variance"],
            "EfficiencyVariance": variance["efficiency_variance"],
            "TotalVariance": variance["total_variance"],
        }
    )

    clinics = inputs.clinics
    dim_clinic = pd.DataFrame(
        {
            "ClinicId": clinics["clinic_id"],
            "ClinicName": clinics["name"],
            "ClinicType": clinics["clinic_type"].map(CLINIC_TYPE_LABELS),
            "Region": clinics["region"],
        }
    )

    months = sorted(budget["month"].unique())
    dim_date = pd.DataFrame(
        {
            "Date": [m.isoformat() for m in months],
            "Year": [m.year for m in months],
            "MonthNumber": [m.month for m in months],
            "MonthName": [MONTH_NAMES[m.month - 1] for m in months],
            "YearMonth": [label(m) for m in months],
            "FiscalYear": [f"FY{m.year + (1 if m.month >= 7 else 0)}" for m in months],
        }
    )

    dim_cost_line = pd.DataFrame(
        {
            "CostLine": list(ALL_LINES),
            "CostLineName": [LINE_LABELS[line] for line in ALL_LINES],
            "Behavior": ["Fixed" if line in FIXED_LINES else "Variable" for line in ALL_LINES],
            "SortOrder": range(1, len(ALL_LINES) + 1),
        }
    )
    dim_visit_type = pd.DataFrame(
        {
            "VisitType": list(VISIT_TYPES),
            "VisitTypeName": [VISIT_TYPE_LABELS[v] for v in VISIT_TYPES],
            "SortOrder": range(1, len(VISIT_TYPES) + 1),
        }
    )

    star = {
        "FactCost": fact_cost,
        "FactVisits": fact_visits,
        "FactBudget": fact_budget,
        "Standards": standards,
        "FactVariance": fact_variance,
        "DimClinic": dim_clinic,
        "DimDate": dim_date,
        "DimCostLine": dim_cost_line,
        "DimVisitType": dim_visit_type,
    }
    return {name: frame[header(name)] for name, frame in star.items()}


def export_star(inputs: Inputs, out_dir: str | Path) -> list[Path]:
    """Write one CSV per star-schema table into `out_dir`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    star = build_star(inputs)
    paths = []
    for name in TABLES:
        path = out / f"{name}.csv"
        star[name].to_csv(path, index=False, lineterminator="\n")
        paths.append(path)
    return paths
