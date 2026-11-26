from __future__ import annotations

import numpy as np
import pytest

from flexbudget.calibrate import calibrate, ols_with_intercepts, standard_cost_per_visit


def test_ols_recovers_exact_slopes_with_clinic_intercepts():
    rng = np.random.default_rng(0)
    x = rng.uniform(10, 100, size=(60, 2))
    groups = np.repeat(np.array(["a", "b", "c"]), 20)
    intercepts = np.where(groups == "a", 500.0, np.where(groups == "b", -200.0, 50.0))
    y = x @ np.array([3.0, 7.5]) + intercepts
    fit = ols_with_intercepts(y, x, groups)
    assert fit.slopes == pytest.approx([3.0, 7.5])
    assert fit.n_obs == 60 and fit.n_params == 5
    assert (fit.std_errors < 1e-8).all()


def test_ols_standard_errors_grow_with_noise():
    rng = np.random.default_rng(1)
    x = rng.uniform(10, 100, size=(80, 2))
    groups = np.repeat(np.array(["a", "b"]), 40)
    clean = x @ np.array([2.0, 5.0])
    quiet = ols_with_intercepts(clean + rng.normal(0, 1, 80), x, groups)
    loud = ols_with_intercepts(clean + rng.normal(0, 20, 80), x, groups)
    assert (loud.std_errors > 5 * quiet.std_errors).all()


def test_ols_rejects_collinear_visit_types():
    x = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0], [4.0, 8.0]])
    with pytest.raises(ValueError, match="rank deficient"):
        ols_with_intercepts(np.arange(4.0), x, np.array(["a", "a", "b", "b"]))


def test_standard_cost_per_visit_prices_labour_as_hours_times_wage(inputs):
    std = standard_cost_per_visit(inputs.standards)
    assert std[("clinical_labour", "preventive")] == pytest.approx(0.55 * 44.0)
    assert std[("medical_supplies", "urgent")] == pytest.approx(20.8)
    assert len(std) == 12


def test_recovers_true_cost_per_visit_within_5_percent(inputs, dataset):
    table = calibrate(inputs)
    truth = dataset.truth["true_cost_per_visit"]
    assert len(table) == 12
    for row in table.itertuples():
        true_cost = truth[row.line][row.visit_type]
        assert abs(row.estimate / true_cost - 1) < 0.05, (row.line, row.visit_type)
        assert row.std_error > 0


def test_flags_only_the_understated_urgent_supply_standard(inputs):
    table = calibrate(inputs)
    flagged = table[table["flag"]]
    assert list(zip(flagged.line, flagged.visit_type, strict=True)) == [
        ("medical_supplies", "urgent")
    ]
    gap = float(flagged["gap"].iloc[0])
    assert -0.25 < gap < -0.15  # a standard 20% below truth


def test_a_wider_tolerance_flags_nothing(inputs):
    assert not calibrate(inputs, tolerance=0.30)["flag"].any()
