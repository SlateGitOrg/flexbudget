"""Reference engine: builds static and flexed budgets and the exact variance decomposition.

The arithmetic lives in `sql/*.sql` and runs in an in-memory DuckDB. This module loads the
inputs, runs the scripts in order and returns the `variance` table, one row per clinic, month
and cost line. Column names come from `flexbudget.metrics`.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import resources

import duckdb
import pandas as pd

from .inputs import Inputs
from .metrics import ENGINE_COLUMNS

IDENTITY_COLUMNS = ("clinic_id", "month", "line")


def _sql_scripts() -> list[tuple[str, str]]:
    folder = resources.files("flexbudget").joinpath("sql")
    files = sorted((p for p in folder.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name)
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def run_engine(inputs: Inputs) -> pd.DataFrame:
    """Run every SQL script against the inputs and return the variance table."""
    con = duckdb.connect(":memory:")
    try:
        for name, frame in inputs.tables().items():
            con.register(f"{name}_df", frame)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
            con.unregister(f"{name}_df")
        for _name, script in _sql_scripts():
            con.execute(script)
        result = con.execute("SELECT * FROM variance").df()
    finally:
        con.close()
    missing = [c for c in ENGINE_COLUMNS if c not in result.columns]
    if missing:
        raise RuntimeError(f"engine output lacks registered metric columns {missing}")
    result["month"] = pd.to_datetime(result["month"]).dt.date
    return result


_ADDITIVE = (
    "static_budget",
    "flexed_budget",
    "flexed_budget_actual_mix",
    "actual_cost",
    "volume_variance",
    "mix_variance",
    "spending_variance",
    "wage_rate_variance",
    "efficiency_variance",
    "total_variance",
)


def rollup(variance: pd.DataFrame, by: Iterable[str]) -> pd.DataFrame:
    """Sum the additive columns over `by` and recompute Variance Pct from the sums."""
    keys = list(by)
    con = duckdb.connect(":memory:")
    try:
        con.register("v", variance)
        sums = ", ".join(f"SUM({c}) AS {c}" for c in _ADDITIVE)
        group = ", ".join(keys)
        out = con.execute(
            f"""
            SELECT {group}, {sums},
                   CASE WHEN SUM(flexed_budget) = 0 THEN NULL
                        ELSE SUM(total_variance) / SUM(flexed_budget) END AS variance_pct
            FROM v
            GROUP BY {group}
            ORDER BY {group}
            """
        ).df()
    finally:
        con.close()
    return out
