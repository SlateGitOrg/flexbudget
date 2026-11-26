"""Deterministic variance commentary.

A clinic-line is flagged for a month when its total variance (actual - static budget) is at least
$5,000 in size and at least 10% of its flexed budget. A closed clinic has a flexed budget of zero,
so only the dollar test applies to it. Each flagged line gets one sentence naming the largest
component and its share of the gross movement (sum of absolute components).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .constants import LINE_LABELS, MATERIAL_PCT, MATERIAL_USD
from .dates import label

COMPONENT_LABELS = {
    "volume_variance": "volume",
    "mix_variance": "mix",
    "spending_variance": "spending",
    "wage_rate_variance": "wage rate",
    "efficiency_variance": "efficiency",
}
GENERAL_COMPONENTS = ("volume_variance", "mix_variance", "spending_variance")
LABOUR_COMPONENTS = ("volume_variance", "mix_variance", "wage_rate_variance", "efficiency_variance")


@dataclass(frozen=True)
class Finding:
    clinic_id: str
    line: str
    month: date
    total_variance: float
    pct_of_flexed: float | None
    component: str
    share: float
    sentence: str


def is_material(total: float, flexed: float) -> bool:
    """The materiality gate: |variance| >= $5,000 and >= 10% of the flexed budget."""
    if abs(total) < MATERIAL_USD:
        return False
    if flexed == 0:
        return True
    return abs(total) >= MATERIAL_PCT * abs(flexed)


def _money(value: float) -> str:
    return f"${abs(value):,.0f}"


def _components_for(line: str) -> tuple[str, ...]:
    return LABOUR_COMPONENTS if line == "clinical_labour" else GENERAL_COMPONENTS


def describe(row: pd.Series) -> Finding:
    total = float(row["total_variance"])
    flexed = float(row["flexed_budget"])
    components = {c: float(row[c]) for c in _components_for(str(row["line"]))}
    dominant = max(components, key=lambda c: (abs(components[c]), c))
    # Components can offset each other, so a share of the net variance can exceed 100% or go
    # negative. The share is of the gross movement (sum of absolute components) and stays in 0-1.
    gross = sum(abs(v) for v in components.values())
    share = abs(components[dominant]) / gross if gross else 0.0
    pct = None if flexed == 0 else total / flexed
    direction = "unfavourable" if total > 0 else "favourable"
    month = row["month"]
    base = f"{row['clinic_id']} {LINE_LABELS[str(row['line'])].lower()}, {label(month)}: "
    if pct is None:
        size = f"{_money(total)} {direction} against a flexed budget of $0"
    else:
        size = f"{_money(total)} {direction} ({abs(pct):.1%} of flexed budget)"
    sentence = (
        f"{base}{size}, mainly {COMPONENT_LABELS[dominant]} ({share:.0%} of the gross variance)."
    )
    return Finding(
        clinic_id=str(row["clinic_id"]),
        line=str(row["line"]),
        month=month,
        total_variance=total,
        pct_of_flexed=pct,
        component=COMPONENT_LABELS[dominant],
        share=share,
        sentence=sentence,
    )


def commentary(variance: pd.DataFrame, month: date) -> list[Finding]:
    """Findings for one month, ordered by size of variance (largest first)."""
    rows = variance[variance["month"] == month]
    findings = [
        describe(row)
        for _, row in rows.iterrows()
        if is_material(float(row["total_variance"]), float(row["flexed_budget"]))
    ]
    return sorted(findings, key=lambda f: (-abs(f.total_variance), f.clinic_id, f.line))
