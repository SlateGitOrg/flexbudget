"""Metric registry: the single list of measure names the SQL engine and the Power BI model share.

Every DAX measure in the semantic model must appear here under the same name, and every
registered metric with an engine column must be produced by the SQL engine. Sign convention for
all variances: positive = unfavourable (actual cost above the budget it is compared with).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    name: str
    column: str | None
    kind: str
    description: str


METRICS: tuple[Metric, ...] = (
    Metric("Actual Cost", "actual_cost", "amount", "Cost recorded in the ledger."),
    Metric(
        "Static Budget",
        "static_budget",
        "amount",
        "Budget at budgeted visits and budgeted mix, plus fixed budgets.",
    ),
    Metric(
        "Flexed Budget",
        "flexed_budget",
        "amount",
        "Budget at actual total visits and budgeted mix, plus fixed budgets.",
    ),
    Metric(
        "Flexed Budget Actual Mix",
        "flexed_budget_actual_mix",
        "amount",
        "Budget at actual visits by type, plus fixed budgets.",
    ),
    Metric(
        "Volume Variance",
        "volume_variance",
        "amount",
        "Flexed budget minus static budget: the cost of seeing more or fewer patients.",
    ),
    Metric(
        "Mix Variance",
        "mix_variance",
        "amount",
        "Budget at actual visits by type minus flexed budget: the cost of a different case mix.",
    ),
    Metric(
        "Spending Variance",
        "spending_variance",
        "amount",
        "Actual cost minus budget at actual visits by type.",
    ),
    Metric(
        "Wage Rate Variance",
        "wage_rate_variance",
        "amount",
        "Clinical labour only: actual hours x (actual rate - standard rate).",
    ),
    Metric(
        "Efficiency Variance",
        "efficiency_variance",
        "amount",
        "Clinical labour only: standard rate x (actual hours - standard hours for actual visits).",
    ),
    Metric("Total Variance", "total_variance", "amount", "Actual cost minus static budget."),
    Metric(
        "Variance Pct",
        "variance_pct",
        "ratio",
        "Total variance divided by flexed budget; blank when the flexed budget is zero.",
    ),
    # Helper measures used inside the DAX above; they have no column of their own.
    Metric("Fixed Budget", None, "amount", "Budget for rent, IT, admin staff and utilities."),
    Metric("Budget Visits", None, "count", "Budgeted visits, any cost line."),
    Metric("Actual Visits", None, "count", "Actual visits."),
)

METRIC_NAMES: frozenset[str] = frozenset(m.name for m in METRICS)
ENGINE_COLUMNS: tuple[str, ...] = tuple(m.column for m in METRICS if m.column)


def by_name(name: str) -> Metric:
    for metric in METRICS:
        if metric.name == name:
            return metric
    raise KeyError(name)
