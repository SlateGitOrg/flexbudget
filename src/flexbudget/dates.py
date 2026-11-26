"""Month helpers. Months travel as ISO first-of-month dates ('2025-03-01') in every file."""

from __future__ import annotations

from datetime import date


def month_start(start: str, index: int) -> date:
    """Date of the 1-based month `index`, counting from `start` ('YYYY-MM')."""
    year, month = (int(part) for part in start.split("-"))
    offset = (month - 1) + (index - 1)
    return date(year + offset // 12, offset % 12 + 1, 1)


def parse_month(text: str) -> date:
    """Accept '2025-03' or '2025-03-01' and return the first of that month."""
    parts = text.split("-")
    if len(parts) not in (2, 3):
        raise ValueError(f"expected YYYY-MM, got {text!r}")
    year, month = int(parts[0]), int(parts[1])
    if not 1 <= month <= 12:
        raise ValueError(f"month out of range in {text!r}")
    return date(year, month, 1)


def label(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"
