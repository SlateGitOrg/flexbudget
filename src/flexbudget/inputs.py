"""Load and sanity-check the input folder written by `flexbudget generate`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import ALL_LINES, VISIT_TYPES

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "clinics": ["clinic_id", "name", "clinic_type", "region"],
    "budget_visits": ["clinic_id", "month", "visit_type", "visits"],
    "standards": ["line", "visit_type", "driver", "value"],
    "fixed_budget": ["clinic_id", "month", "line", "amount"],
    "actual_cost": ["clinic_id", "month", "line", "amount"],
    "actual_hours": ["clinic_id", "month", "hours"],
    "actual_visits": ["clinic_id", "month", "visit_type", "visits"],
}


class InputError(ValueError):
    """The input folder is missing a file, a column or a value the engine needs."""


@dataclass
class Inputs:
    clinics: pd.DataFrame
    budget_visits: pd.DataFrame
    standards: pd.DataFrame
    fixed_budget: pd.DataFrame
    actual_cost: pd.DataFrame
    actual_hours: pd.DataFrame
    actual_visits: pd.DataFrame
    truth: dict[str, Any] | None = None

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in REQUIRED_COLUMNS}


def load_inputs(folder: str | Path) -> Inputs:
    folder = Path(folder)
    frames: dict[str, pd.DataFrame] = {}
    for name, columns in REQUIRED_COLUMNS.items():
        path = folder / f"{name}.csv"
        if not path.exists():
            raise InputError(f"missing input file {path}")
        df = pd.read_csv(path)
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise InputError(f"{path.name} is missing columns {missing}")
        if "month" in df.columns:
            df["month"] = pd.to_datetime(df["month"]).dt.date
        frames[name] = df
    unknown_lines = set(frames["actual_cost"]["line"]) - set(ALL_LINES)
    unknown_types = set(frames["actual_visits"]["visit_type"]) - set(VISIT_TYPES)
    if unknown_lines or unknown_types:
        raise InputError(
            f"unknown lines {sorted(unknown_lines)} or visit types {sorted(unknown_types)}"
        )
    truth_path = folder / "truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8")) if truth_path.exists() else None
    return Inputs(truth=truth, **frames)
