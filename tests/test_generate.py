from __future__ import annotations

from datetime import date

import pytest

from flexbudget.dates import label, month_start, parse_month
from flexbudget.generate import allocate, generate, write_dataset
from flexbudget.inputs import InputError, load_inputs


def test_shape_matches_the_brief(dataset):
    assert dataset.clinics["clinic_id"].nunique() == 18
    assert dataset.budget_visits["month"].nunique() == 24
    assert len(dataset.budget_visits) == 18 * 24 * 4
    assert len(dataset.actual_visits) == len(dataset.budget_visits)
    assert dataset.actual_cost["line"].nunique() == 7
    assert len(dataset.actual_cost) == 18 * 24 * 7
    assert dataset.budget_visits["month"].min() == "2023-07-01"
    assert dataset.budget_visits["month"].max() == "2025-06-01"


def test_same_seed_is_identical_and_other_seed_differs():
    a, b, c = generate(7), generate(7), generate(8)
    assert a.actual_cost.equals(b.actual_cost)
    assert a.actual_visits.equals(b.actual_visits)
    assert not a.actual_cost.equals(c.actual_cost)


def test_urgent_supply_standard_is_20_percent_below_truth(dataset):
    standards = dataset.standards
    row = standards[
        (standards["line"] == "medical_supplies")
        & (standards["visit_type"] == "urgent")
        & (standards["driver"] == "usd_per_visit")
    ]
    truth = dataset.truth["true_cost_per_visit"]["medical_supplies"]["urgent"]
    assert float(row["value"].iloc[0]) == pytest.approx(0.8 * truth)
    assert dataset.truth["standard_errors"][0]["standard_to_truth"] == 0.8


def test_truth_lists_the_injected_clinic_lines_for_march_2025(dataset):
    active = {(e["clinic"], e["line"]) for e in dataset.truth["active_by_month"]["2025-03"]}
    assert active == {
        ("C07", "clinical_labour"),
        ("C07", "medical_supplies"),
        ("C07", "lab_sendouts"),
        ("C12", "medical_supplies"),
        ("C03", "medical_supplies"),
    }


def test_c15_agency_wages_window_in_truth(dataset):
    for month in ("2024-10", "2024-11", "2024-12"):
        assert any(e["clinic"] == "C15" for e in dataset.truth["active_by_month"][month])
    assert not any(e["clinic"] == "C15" for e in dataset.truth["active_by_month"]["2025-01"])
    assert not any(e["clinic"] == "C15" for e in dataset.truth["active_by_month"]["2024-09"])


def test_c09_is_closed_in_month_20_but_still_pays_fixed_costs(dataset):
    visits = dataset.actual_visits
    closed = visits[(visits["clinic_id"] == "C09") & (visits["month"] == "2025-02-01")]
    assert closed["visits"].sum() == 0
    cost = dataset.actual_cost
    rows = cost[(cost["clinic_id"] == "C09") & (cost["month"] == "2025-02-01")]
    by_line = rows.set_index("line")["amount"]
    assert by_line[["medical_supplies", "lab_sendouts", "clinical_labour"]].sum() == 0
    assert (by_line[["rent", "it", "admin_staff", "utilities"]] > 0).all()


def test_c07_variable_costs_sit_exactly_on_the_standards(dataset):
    visits = dataset.actual_visits
    month = "2025-03-01"
    v = visits[(visits["clinic_id"] == "C07") & (visits["month"] == month)].set_index("visit_type")
    std = dataset.standards
    sup = std[(std["line"] == "medical_supplies") & (std["driver"] == "usd_per_visit")]
    sup = sup.set_index("visit_type")["value"]
    expected = sum(v.loc[t, "visits"] * sup[t] for t in sup.index)
    cost = dataset.actual_cost
    actual = cost[
        (cost["clinic_id"] == "C07")
        & (cost["month"] == month)
        & (cost["line"] == "medical_supplies")
    ]["amount"].iloc[0]
    assert actual == pytest.approx(expected, abs=0.01)


def test_allocate_keeps_the_total_and_the_proportions():
    parts = allocate(101, [0.5, 0.3, 0.2])
    assert sum(parts) == 101
    assert parts == [51, 30, 20]
    assert allocate(0, [1, 2]) == [0, 0]


def test_month_helpers():
    assert month_start("2023-07", 1) == date(2023, 7, 1)
    assert month_start("2023-07", 13) == date(2024, 7, 1)
    assert month_start("2023-07", 24) == date(2025, 6, 1)
    assert parse_month("2025-03") == date(2025, 3, 1)
    assert parse_month("2025-03-17") == date(2025, 3, 1)
    assert label(date(2025, 3, 1)) == "2025-03"
    with pytest.raises(ValueError):
        parse_month("2025-13")


def test_write_then_load_round_trips(dataset, tmp_path):
    write_dataset(dataset, tmp_path)
    loaded = load_inputs(tmp_path)
    assert len(loaded.actual_cost) == len(dataset.actual_cost)
    assert loaded.truth["seed"] == 7
    assert loaded.budget_visits["month"].iloc[0] == date(2023, 7, 1)


def test_load_reports_a_missing_file(tmp_path):
    with pytest.raises(InputError, match="missing input file"):
        load_inputs(tmp_path)
