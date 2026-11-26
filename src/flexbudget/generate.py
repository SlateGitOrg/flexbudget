"""Seeded synthetic data for an 18-clinic outpatient network.

The generator holds the true cost drivers and writes only what a finance system would hold:
visits, budgets, standards and ledger actuals. The injected patterns are recorded in
`truth.json`, which the tests use to check the analysis recovers them.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .constants import (
    DRIVER_HOURS_PER_VISIT,
    DRIVER_USD_PER_HOUR,
    DRIVER_USD_PER_VISIT,
    FIXED_LINES,
    VISIT_TYPES,
    WAGE_VISIT_TYPE,
)
from .dates import label, month_start

DEFAULT_SCENARIO = Path(__file__).with_name("network.yaml")

INPUT_FILES = (
    "clinics.csv",
    "budget_visits.csv",
    "standards.csv",
    "fixed_budget.csv",
    "actual_cost.csv",
    "actual_hours.csv",
    "actual_visits.csv",
    "truth.json",
)


@dataclass
class Dataset:
    clinics: pd.DataFrame
    budget_visits: pd.DataFrame
    standards: pd.DataFrame
    fixed_budget: pd.DataFrame
    actual_cost: pd.DataFrame
    actual_hours: pd.DataFrame
    actual_visits: pd.DataFrame
    truth: dict[str, Any]


def load_scenario(path: Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_SCENARIO, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def allocate(total: int, weights: list[float]) -> list[int]:
    """Split an integer `total` in proportion to `weights` (largest-remainder method)."""
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0] * len(weights)
    raw = [total * w / weight_sum for w in weights]
    floors = [math.floor(x) for x in raw]
    short = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (floors[i] - raw[i], i))
    for i in order[:short]:
        floors[i] += 1
    return floors


def _clip_normal(rng: np.random.Generator, sd: float, limit_sds: float = 2.5) -> float:
    return float(np.clip(rng.normal(0.0, sd), -limit_sds * sd, limit_sds * sd))


def _cost_noise(rng: np.random.Generator, half_width: float) -> float:
    """Relative noise on a cost line: uniform within +/- `half_width` (2% means within 2%)."""
    return float(rng.uniform(-half_width, half_width))


def _season(scenario: dict[str, Any], visit_type: str, month: date) -> float:
    value = 1.0
    for harmonic in scenario["seasonality"][visit_type]:
        angle = 2 * math.pi * (month.month - harmonic["peak_month"]) / harmonic["period"]
        value += harmonic["amplitude"] * math.cos(angle)
    return value


def _standards_table(scenario: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Standards rows plus the standard per-visit unit values keyed by driver group."""
    rows: list[dict[str, Any]] = []
    offsets = scenario["standard_offset"]
    std: dict[str, dict[str, float]] = {}
    for line, truth in scenario["true_cost_per_visit"].items():
        std[line] = {}
        for vt in VISIT_TYPES:
            value = round(truth[vt] * (1 + offsets[line][vt]), 4)
            std[line][vt] = value
            rows.append(
                {
                    "line": line,
                    "visit_type": vt,
                    "driver": DRIVER_USD_PER_VISIT,
                    "value": value,
                }
            )
    std["hours"] = {}
    for vt in VISIT_TYPES:
        value = round(scenario["true_hours_per_visit"][vt] * (1 + offsets["clinical_hours"][vt]), 4)
        std["hours"][vt] = value
        rows.append(
            {
                "line": "clinical_labour",
                "visit_type": vt,
                "driver": DRIVER_HOURS_PER_VISIT,
                "value": value,
            }
        )
    rows.append(
        {
            "line": "clinical_labour",
            "visit_type": WAGE_VISIT_TYPE,
            "driver": DRIVER_USD_PER_HOUR,
            "value": float(scenario["wage_standard"]),
        }
    )
    return pd.DataFrame(rows), std


def generate(seed: int = 7, scenario: dict[str, Any] | None = None) -> Dataset:
    scenario = scenario or load_scenario()
    rng = np.random.default_rng(seed)
    n_months = int(scenario["months"])
    months = [month_start(scenario["start_month"], i) for i in range(1, n_months + 1)]
    clinics = scenario["clinics"]
    noise = scenario["noise"]
    inj = scenario["injections"]
    wage_std = float(scenario["wage_standard"])
    true_sup = scenario["true_cost_per_visit"]["medical_supplies"]
    true_lab = scenario["true_cost_per_visit"]["lab_sendouts"]
    true_hours = scenario["true_hours_per_visit"]
    standards_df, std = _standards_table(scenario)

    budget_rows: list[tuple[str, date, str, int]] = []
    actual_rows: list[tuple[str, date, str, int]] = []
    cost_rows: list[tuple[str, date, str, float]] = []
    hours_rows: list[tuple[str, date, float]] = []
    fixed_rows: list[tuple[str, date, str, float]] = []

    for clinic in clinics:
        cid = clinic["id"]
        kind = clinic["type"]
        base_mix = scenario["budget_mix_override"].get(cid) or scenario["mix"][kind]
        if cid in scenario["budget_mix_override"]:
            mix = [float(base_mix[vt]) for vt in VISIT_TYPES]
        else:
            raw = [base_mix[vt] * (1 + _clip_normal(rng, 0.08, 1.9)) for vt in VISIT_TYPES]
            mix = [x / sum(raw) for x in raw]
        wage_factor = _clip_normal(rng, noise["clinic_wage_factor"], 2.0)
        eff_factor = _clip_normal(rng, noise["clinic_efficiency_factor"], 2.0)
        fixed_scale = round((clinic["base_visits"] / 2500) ** 0.5 * 100) / 100

        for idx, month in enumerate(months, start=1):
            growth = (1 + scenario["budget_growth_per_year"]) ** ((idx - 1) / 12)
            budget = [
                int(round(clinic["base_visits"] * growth * _season(scenario, vt, month) * share))
                for vt, share in zip(VISIT_TYPES, mix, strict=True)
            ]
            budget_total = sum(budget)
            budget_share = [b / budget_total for b in budget]

            # Random draws are taken for every clinic-month so overrides never shift the stream.
            e_cm = _clip_normal(rng, noise["volume_clinic_month"], 2.0)
            e_ct = [_clip_normal(rng, noise["volume_type"], 2.0) for _ in VISIT_TYPES]
            eta_sup = _cost_noise(rng, noise["cost"])
            eta_lab = _cost_noise(rng, noise["cost"])
            eta_hours = _cost_noise(rng, noise["cost"])
            eta_rate = _cost_noise(rng, noise["cost"] / 2)
            eta_fixed = {line: _cost_noise(rng, noise["cost"]) for line in FIXED_LINES}

            # The clinic-month surprise scales total volume; the per-type surprise only reshuffles
            # the mix, so a clinic's total volume is never moved by it.
            actual = allocate(
                round(budget_total * (1 + e_cm)),
                [s * (1 + e) for s, e in zip(budget_share, e_ct, strict=True)],
            )
            at_standard = False  # variable costs priced exactly at the budget standards
            if (
                cid == inj["volume_surge"]["clinic"]
                and idx >= inj["volume_surge"]["first_month_index"]
            ):
                actual = allocate(round(budget_total * inj["volume_surge"]["factor"]), budget_share)
                at_standard = True
            elif cid == inj["supply_overspend"]["clinic"] and (
                idx >= inj["supply_overspend"]["first_month_index"]
            ):
                actual = list(budget)
            elif cid == inj["mix_shift"]["clinic"] and idx >= inj["mix_shift"]["first_month_index"]:
                ms = inj["mix_shift"]
                span = ms["end_month_index"] - (ms["first_month_index"] - 1)
                ramp = 1 + (ms["end_share"] / ms["start_share"] - 1) * (
                    (idx - (ms["first_month_index"] - 1)) / span
                )
                u = VISIT_TYPES.index("urgent")
                urgent_share = budget_share[u] * ramp
                rest = sum(s for i, s in enumerate(budget_share) if i != u)
                weights = [
                    urgent_share if i == u else s * (1 - urgent_share) / rest
                    for i, s in enumerate(budget_share)
                ]
                actual = allocate(round(budget_total * (1 + e_cm)), weights)
            closed = cid == inj["closure"]["clinic"] and idx == inj["closure"]["month_index"]
            if closed:
                actual = [0] * len(VISIT_TYPES)

            for vt, b, a in zip(VISIT_TYPES, budget, actual, strict=True):
                budget_rows.append((cid, month, vt, b))
                actual_rows.append((cid, month, vt, a))

            # Variable costs.
            sup_truth = sum(a * true_sup[vt] for vt, a in zip(VISIT_TYPES, actual, strict=True))
            lab_truth = sum(a * true_lab[vt] for vt, a in zip(VISIT_TYPES, actual, strict=True))
            hours_truth = sum(a * true_hours[vt] for vt, a in zip(VISIT_TYPES, actual, strict=True))
            sup_std = sum(
                a * std["medical_supplies"][vt] for vt, a in zip(VISIT_TYPES, actual, strict=True)
            )
            lab_std = sum(
                a * std["lab_sendouts"][vt] for vt, a in zip(VISIT_TYPES, actual, strict=True)
            )
            hours_std = sum(a * std["hours"][vt] for vt, a in zip(VISIT_TYPES, actual, strict=True))

            supplies = sup_truth * (1 + eta_sup)
            lab = lab_truth * (1 + eta_lab)
            hours = hours_truth * (1 + eff_factor) * (1 + eta_hours)
            payroll = hours * wage_std * (1 + wage_factor) * (1 + eta_rate)
            if at_standard:
                supplies, lab, hours = sup_std, lab_std, hours_std
                payroll = hours * wage_std
            if (
                cid == inj["supply_overspend"]["clinic"]
                and idx >= inj["supply_overspend"]["first_month_index"]
            ):
                supplies = sup_std * inj["supply_overspend"]["factor"]
            aw = inj["agency_wages"]
            if cid == aw["clinic"] and aw["first_month_index"] <= idx <= aw["last_month_index"]:
                hours = hours_std
                payroll = hours * wage_std * aw["factor"]
            if closed:
                supplies = lab = hours = payroll = 0.0

            cost_rows.append((cid, month, "medical_supplies", round(supplies, 2)))
            cost_rows.append((cid, month, "lab_sendouts", round(lab, 2)))
            cost_rows.append((cid, month, "clinical_labour", round(payroll, 2)))
            hours_rows.append((cid, month, round(hours, 2)))

            # Fixed lines.
            second_year = 1.03 if idx > 12 else 1.0
            for line in FIXED_LINES:
                monthly = scenario["fixed_monthly"][line][kind] * fixed_scale * second_year
                if line == "utilities":
                    angle = 2 * math.pi * (month.month - 1) / 12
                    monthly *= 1 + scenario["utilities_seasonal_amplitude"] * math.cos(angle)
                budget_amt = round(monthly / 100) * 100
                fixed_rows.append((cid, month, line, float(budget_amt)))
                cost_rows.append((cid, month, line, round(budget_amt * (1 + eta_fixed[line]), 2)))

    def frame(rows: list[tuple], cols: list[str]) -> pd.DataFrame:
        out = pd.DataFrame(rows, columns=cols)
        out["month"] = pd.to_datetime(out["month"]).dt.strftime("%Y-%m-%d")
        return out

    clinics_df = pd.DataFrame(
        [
            {
                "clinic_id": c["id"],
                "name": c["name"],
                "clinic_type": c["type"],
                "region": c["region"],
            }
            for c in clinics
        ]
    )
    dataset = Dataset(
        clinics=clinics_df,
        budget_visits=frame(budget_rows, ["clinic_id", "month", "visit_type", "visits"]),
        standards=standards_df,
        fixed_budget=frame(fixed_rows, ["clinic_id", "month", "line", "amount"]),
        actual_cost=frame(cost_rows, ["clinic_id", "month", "line", "amount"]),
        actual_hours=frame(hours_rows, ["clinic_id", "month", "hours"]),
        actual_visits=frame(actual_rows, ["clinic_id", "month", "visit_type", "visits"]),
        truth=_truth(scenario, months, seed),
    )
    return dataset


def _truth(scenario: dict[str, Any], months: list[date], seed: int) -> dict[str, Any]:
    inj = scenario["injections"]
    wage = float(scenario["wage_standard"])
    true_cost = {
        "medical_supplies": dict(scenario["true_cost_per_visit"]["medical_supplies"]),
        "lab_sendouts": dict(scenario["true_cost_per_visit"]["lab_sendouts"]),
        "clinical_labour": {
            vt: round(scenario["true_hours_per_visit"][vt] * wage, 4) for vt in VISIT_TYPES
        },
    }
    variable = ["clinical_labour", "medical_supplies", "lab_sendouts"]
    effects = [
        {
            "kind": "volume_surge",
            "clinic": inj["volume_surge"]["clinic"],
            "lines": variable,
            "first_month_index": inj["volume_surge"]["first_month_index"],
            "last_month_index": len(months),
        },
        {
            "kind": "supply_overspend",
            "clinic": inj["supply_overspend"]["clinic"],
            "lines": ["medical_supplies"],
            "first_month_index": inj["supply_overspend"]["first_month_index"],
            "last_month_index": len(months),
        },
        {
            "kind": "mix_shift",
            "clinic": inj["mix_shift"]["clinic"],
            "lines": ["medical_supplies"],
            "first_month_index": inj["mix_shift"]["first_month_index"],
            "last_month_index": len(months),
        },
        {
            "kind": "agency_wages",
            "clinic": inj["agency_wages"]["clinic"],
            "lines": ["clinical_labour"],
            "first_month_index": inj["agency_wages"]["first_month_index"],
            "last_month_index": inj["agency_wages"]["last_month_index"],
        },
        {
            "kind": "closure",
            "clinic": inj["closure"]["clinic"],
            "lines": variable,
            "first_month_index": inj["closure"]["month_index"],
            "last_month_index": inj["closure"]["month_index"],
        },
    ]
    active: dict[str, list[dict[str, str]]] = {}
    for idx, month in enumerate(months, start=1):
        entries = [
            {"clinic": e["clinic"], "line": line, "kind": e["kind"]}
            for e in effects
            if e["first_month_index"] <= idx <= e["last_month_index"]
            for line in e["lines"]
        ]
        active[label(month)] = entries
    for effect in effects:
        effect["first_month"] = label(months[effect["first_month_index"] - 1])
        effect["last_month"] = label(months[effect["last_month_index"] - 1])
    return {
        "seed": seed,
        "wage_standard": wage,
        "true_cost_per_visit": true_cost,
        "true_hours_per_visit": dict(scenario["true_hours_per_visit"]),
        "standard_errors": [
            {
                "line": "medical_supplies",
                "visit_type": "urgent",
                "standard_to_truth": round(
                    1 + scenario["standard_offset"]["medical_supplies"]["urgent"], 4
                ),
            }
        ],
        "effects": effects,
        "active_by_month": active,
    }


def write_dataset(dataset: Dataset, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    frames = {
        "clinics.csv": dataset.clinics,
        "budget_visits.csv": dataset.budget_visits,
        "standards.csv": dataset.standards,
        "fixed_budget.csv": dataset.fixed_budget,
        "actual_cost.csv": dataset.actual_cost,
        "actual_hours.csv": dataset.actual_hours,
        "actual_visits.csv": dataset.actual_visits,
    }
    for name, df in frames.items():
        path = out_dir / name
        df.to_csv(path, index=False, lineterminator="\n")
        written.append(path)
    truth_path = out_dir / "truth.json"
    truth_path.write_text(json.dumps(dataset.truth, indent=2) + "\n", encoding="utf-8")
    written.append(truth_path)
    return written
