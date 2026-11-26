from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from flexbudget.constants import FIXED_LINES, VARIABLE_LINES, VISIT_TYPES
from flexbudget.engine import rollup, run_engine
from flexbudget.inputs import Inputs
from flexbudget.metrics import ENGINE_COLUMNS

MONTH = date(2025, 1, 1)


def _hand_inputs() -> Inputs:
    """One clinic, one month, numbers small enough to check by hand."""
    types = list(VISIT_TYPES)
    budget = [100, 100, 100, 100]
    actual = [160, 110, 70, 100]
    standards = []
    for line, values in (
        ("medical_supplies", [5, 10, 20, 40]),
        ("lab_sendouts", [1, 2, 3, 4]),
    ):
        for vt, v in zip(types, values, strict=True):
            standards.append((line, vt, "usd_per_visit", v))
    for vt, v in zip(types, [0.5, 0.5, 1.0, 2.0], strict=True):
        standards.append(("clinical_labour", vt, "hours_per_visit", v))
    standards.append(("clinical_labour", "ALL", "usd_per_hour", 40.0))
    cost = [
        ("C1", MONTH, "medical_supplies", 7800.0),
        ("C1", MONTH, "lab_sendouts", 1050.0),
        ("C1", MONTH, "clinical_labour", 17220.0),
        ("C1", MONTH, "rent", 1030.0),
    ]
    return Inputs(
        clinics=pd.DataFrame(
            [{"clinic_id": "C1", "name": "One", "clinic_type": "primary", "region": "N"}]
        ),
        budget_visits=pd.DataFrame(
            [("C1", MONTH, t, v) for t, v in zip(types, budget, strict=True)],
            columns=["clinic_id", "month", "visit_type", "visits"],
        ),
        standards=pd.DataFrame(standards, columns=["line", "visit_type", "driver", "value"]),
        fixed_budget=pd.DataFrame(
            [("C1", MONTH, "rent", 1000.0)], columns=["clinic_id", "month", "line", "amount"]
        ),
        actual_cost=pd.DataFrame(cost, columns=["clinic_id", "month", "line", "amount"]),
        actual_hours=pd.DataFrame([("C1", MONTH, 420.0)], columns=["clinic_id", "month", "hours"]),
        actual_visits=pd.DataFrame(
            [("C1", MONTH, t, v) for t, v in zip(types, actual, strict=True)],
            columns=["clinic_id", "month", "visit_type", "visits"],
        ),
    )


def _at(df, clinic, month):
    return df[(df["clinic_id"] == clinic) & (df["month"] == month)]


def _row(df, line):
    return df[df["line"] == line].iloc[0]


def test_hand_computed_supplies_split():
    out = run_engine(_hand_inputs())
    r = _row(out, "medical_supplies")
    # static 7,500; flexed 440 x 18.75 = 8,250; at actual mix 7,300; actual 7,800
    assert (r.static_budget, r.flexed_budget, r.flexed_budget_actual_mix) == (7500, 8250, 7300)
    assert (r.volume_variance, r.mix_variance, r.spending_variance) == (750, -950, 500)
    assert r.total_variance == 300


def test_hand_computed_labour_split_into_wage_and_efficiency():
    out = run_engine(_hand_inputs())
    r = _row(out, "clinical_labour")
    # static 16,000; flexed 17,600; at actual mix 405 standard hours x 40 = 16,200
    assert (r.static_budget, r.flexed_budget, r.flexed_budget_actual_mix) == (16000, 17600, 16200)
    assert r.spending_variance == 1020
    assert r.wage_rate_variance == 420  # 17,220 - 420 h x 40
    assert r.efficiency_variance == 600  # 40 x (420 h - 405 h)
    assert r.total_variance == 1220


def test_hand_computed_fixed_line_carries_spending_only():
    r = _row(run_engine(_hand_inputs()), "rent")
    assert (r.volume_variance, r.mix_variance, r.spending_variance) == (0, 0, 30)
    assert pd.isna(r.wage_rate_variance) and pd.isna(r.efficiency_variance)


def test_decomposition_is_exact_for_every_clinic_line_month(variance):
    parts = variance.volume_variance + variance.mix_variance + variance.spending_variance
    assert len(variance) == 18 * 24 * 7
    assert (parts - (variance.actual_cost - variance.static_budget)).abs().max() < 0.01
    assert (
        variance.total_variance - (variance.actual_cost - variance.static_budget)
    ).abs().max() < (0.0051)


def test_labour_wage_plus_efficiency_equals_labour_spending(variance):
    labour = variance[variance.line == "clinical_labour"]
    gap = labour.wage_rate_variance + labour.efficiency_variance - labour.spending_variance
    assert gap.abs().max() < 0.01
    assert variance[variance.line != "clinical_labour"].wage_rate_variance.isna().all()


def test_fixed_lines_have_no_volume_or_mix_variance(variance):
    fixed = variance[variance.line.isin(FIXED_LINES)]
    assert (fixed.volume_variance == 0).all() and (fixed.mix_variance == 0).all()
    assert (fixed.spending_variance - fixed.total_variance).abs().max() < 0.01


def test_c07_variance_is_volume_not_spending(variance, inputs):
    rows = variance[
        (variance.clinic_id == "C07")
        & (variance.line.isin(VARIABLE_LINES))
        & (variance.month >= date(2024, 7, 1))
    ]
    assert len(rows) == 12 * 3
    assert (rows.spending_variance.abs() < 0.01 * rows.volume_variance.abs()).all()
    assert (rows.volume_variance > 0).all()

    # volume variance = change in visits x standard cost per visit at the budget mix
    month = date(2025, 3, 1)
    bud = inputs.budget_visits.pipe(_at, "C07", month)
    act = inputs.actual_visits.pipe(_at, "C07", month)
    std = inputs.standards
    wage = float(std[std.driver == "usd_per_hour"].value.iloc[0])
    cost_per_type = {}
    for r in std[std.driver != "usd_per_hour"].itertuples():
        factor = wage if r.driver == "hours_per_visit" else 1.0
        cost_per_type[(r.line, r.visit_type)] = r.value * factor
    for line in VARIABLE_LINES:
        total_b, total_a = bud.visits.sum(), act.visits.sum()
        avg = sum(
            row.visits / total_b * cost_per_type[(line, row.visit_type)] for row in bud.itertuples()
        )
        expected = (total_a - total_b) * avg
        got = variance.query("clinic_id == 'C07' and month == @month and line == @line")
        assert got.volume_variance.iloc[0] == pytest.approx(expected, abs=0.02)


def test_c12_supplies_spending_is_18_percent_of_flexed(variance):
    rows = variance[
        (variance.clinic_id == "C12")
        & (variance.line == "medical_supplies")
        & (variance.month >= date(2024, 9, 1))
    ]
    assert len(rows) == 10
    share = rows.spending_variance / rows.flexed_budget_actual_mix
    assert ((share > 0.16) & (share < 0.20)).all()
    assert (rows.volume_variance.abs() < 0.01).all() and (rows.mix_variance.abs() < 0.01).all()


def test_c03_mix_variance_is_unfavourable_and_matches_a_hand_calculation(variance, inputs):
    c03 = variance[(variance.clinic_id == "C03") & (variance.month >= date(2024, 7, 1))]
    monthly = c03[c03.line.isin(VARIABLE_LINES)].groupby("month").mix_variance.sum()
    assert len(monthly) == 12 and (monthly > 0).all()

    month = date(2024, 7, 1)
    bud = inputs.budget_visits.pipe(_at, "C03", month).set_index("visit_type")
    act = inputs.actual_visits.pipe(_at, "C03", month).set_index("visit_type")
    total_a = act.visits.sum()
    std = inputs.standards
    wage = float(std[std.driver == "usd_per_hour"].value.iloc[0])
    expected = 0.0
    for r in std[std.driver != "usd_per_hour"].itertuples():
        factor = wage if r.driver == "hours_per_visit" else 1.0
        d_share = act.visits[r.visit_type] / total_a - bud.visits[r.visit_type] / bud.visits.sum()
        expected += d_share * total_a * r.value * factor
    got = c03[(c03.month == month) & c03.line.isin(VARIABLE_LINES)].mix_variance.sum()
    assert got == pytest.approx(expected, abs=0.05)


def test_c03_urgent_share_ramps_from_budget_to_double(inputs):
    def urgent_share(frame):
        v = frame.query("clinic_id == 'C03'")
        return (
            v[v.visit_type == "urgent"].set_index("month").visits / v.groupby("month").visits.sum()
        )

    ratio = urgent_share(inputs.actual_visits) / urgent_share(inputs.budget_visits)
    assert ratio[date(2024, 7, 1)] == pytest.approx(1 + 1 / 12, abs=0.01)
    assert ratio[date(2025, 6, 1)] == pytest.approx(2.0, abs=0.01)
    assert ratio[date(2024, 6, 1)] == pytest.approx(
        1.0, abs=0.35
    )  # ordinary noise before the shift


def test_c15_wage_variance_is_the_agency_premium_and_efficiency_is_nil(variance):
    rows = variance[
        (variance.clinic_id == "C15")
        & (variance.line == "clinical_labour")
        & (variance.month.isin([date(2024, 10, 1), date(2024, 11, 1), date(2024, 12, 1)]))
    ]
    assert len(rows) == 3
    wage_std = 44.0
    for r in rows.itertuples():
        assert r.wage_rate_variance == pytest.approx(r.actual_hours * 0.12 * wage_std, rel=0.01)
        assert abs(r.efficiency_variance) < 1.0


def test_closed_clinic_has_zero_flexed_variable_budget_and_null_pct(variance):
    rows = variance[(variance.clinic_id == "C09") & (variance.month == date(2025, 2, 1))]
    variable = rows[rows.line.isin(VARIABLE_LINES)]
    assert (variable.flexed_budget == 0).all()
    assert variable.variance_pct.isna().all()
    assert (variable.volume_variance == -variable.static_budget).all()
    fixed = rows[rows.line.isin(FIXED_LINES)]
    assert fixed.variance_pct.notna().all()


def test_variance_pct_is_never_infinite(variance):
    assert variance.variance_pct.dropna().abs().lt(float("inf")).all()


def test_rollup_recomputes_the_ratio_from_sums(variance):
    month = variance[variance.month == date(2025, 3, 1)]
    out = rollup(month, ["clinic_id"])
    row = out[out.clinic_id == "C07"].iloc[0]
    mine = month[month.clinic_id == "C07"]
    assert row.total_variance == pytest.approx(mine.total_variance.sum())
    assert row.variance_pct == pytest.approx(mine.total_variance.sum() / mine.flexed_budget.sum())
    closed = rollup(variance[variance.clinic_id == "C09"], ["month"])
    assert closed.variance_pct.notna().all()


def test_engine_output_has_every_registered_column(variance):
    assert set(ENGINE_COLUMNS) <= set(variance.columns)
