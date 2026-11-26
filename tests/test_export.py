from __future__ import annotations

import filecmp
from pathlib import Path

import pandas as pd

from flexbudget.export import build_star, export_star
from flexbudget.starschema import TABLES, header

REPO = Path(__file__).resolve().parents[1]


def test_export_writes_nine_tables_with_the_schema_headers(inputs, tmp_path):
    paths = export_star(inputs, tmp_path)
    assert sorted(p.stem for p in paths) == sorted(TABLES)
    assert len(paths) == 9
    for path in paths:
        assert list(pd.read_csv(path, nrows=0).columns) == header(path.stem)


def test_fact_variance_round_trips_to_the_engine_output(inputs, variance, tmp_path):
    export_star(inputs, tmp_path)
    back = pd.read_csv(tmp_path / "FactVariance.csv")
    assert len(back) == len(variance)
    for column, source in (
        ("VolumeVariance", "volume_variance"),
        ("MixVariance", "mix_variance"),
        ("SpendingVariance", "spending_variance"),
        ("TotalVariance", "total_variance"),
        ("ActualCost", "actual_cost"),
        ("StaticBudget", "static_budget"),
        ("FlexedBudget", "flexed_budget"),
    ):
        assert abs(back[column].sum() - variance[source].sum()) < 0.005, column
    labour = back[back.CostLine == "clinical_labour"]
    engine_labour = variance[variance.line == "clinical_labour"]
    assert abs(labour.WageRateVariance.sum() - engine_labour.wage_rate_variance.sum()) < 0.005
    assert abs(labour.EfficiencyVariance.sum() - engine_labour.efficiency_variance.sum()) < 0.005
    per_clinic = back.groupby("ClinicId").TotalVariance.sum()
    engine_clinic = variance.groupby("clinic_id").total_variance.sum()
    assert (per_clinic - engine_clinic).abs().max() < 0.005


def test_fact_budget_holds_visit_rows_and_fixed_rows_separately(inputs):
    budget = build_star(inputs)["FactBudget"]
    visit_rows = budget[budget.CostLine == ""]
    fixed_rows = budget[budget.VisitType == ""]
    assert len(visit_rows) == 18 * 24 * 4 and len(fixed_rows) == 18 * 24 * 4
    assert visit_rows.BudgetVisits.sum() == inputs.budget_visits.visits.sum()
    assert fixed_rows.FixedBudget.sum() == inputs.fixed_budget.amount.sum()


def test_hours_exist_only_on_labour_rows(inputs):
    cost = build_star(inputs)["FactCost"]
    assert cost[cost.CostLine == "clinical_labour"].ActualHours.notna().all()
    assert cost[cost.CostLine != "clinical_labour"].ActualHours.isna().all()
    assert abs(cost.ActualCost.sum() - inputs.actual_cost.amount.sum()) < 0.005


def test_dimensions(inputs):
    star = build_star(inputs)
    dates = star["DimDate"]
    assert len(dates) == 24
    assert dates.loc[dates.Date == "2024-07-01", "FiscalYear"].iloc[0] == "FY2025"
    assert dates.loc[dates.Date == "2024-06-01", "FiscalYear"].iloc[0] == "FY2024"
    clinics = star["DimClinic"]
    assert set(clinics.ClinicType) == {"Primary care", "Urgent care"}
    lines = star["DimCostLine"].set_index("CostLine").Behavior
    assert lines["rent"] == "Fixed" and lines["clinical_labour"] == "Variable"
    standards = star["Standards"]
    assert len(standards) == 12
    assert standards[standards.CostLine == "clinical_labour"].StdWageRate.eq(44.0).all()


def test_shipped_star_csvs_match_a_fresh_export(inputs, tmp_path):
    export_star(inputs, tmp_path)
    for name in TABLES:
        assert filecmp.cmp(tmp_path / f"{name}.csv", REPO / "powerbi" / "data" / f"{name}.csv"), (
            name
        )
