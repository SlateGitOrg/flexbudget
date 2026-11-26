"""Names shared by the generator, the SQL engine, the exporter and the validator."""

from __future__ import annotations

VISIT_TYPES: tuple[str, ...] = ("preventive", "sick", "urgent", "procedure")

# Cost lines whose budget moves with visits (labour is priced per hour, the others per visit).
VARIABLE_LINES: tuple[str, ...] = ("clinical_labour", "medical_supplies", "lab_sendouts")
FIXED_LINES: tuple[str, ...] = ("rent", "it", "admin_staff", "utilities")
ALL_LINES: tuple[str, ...] = VARIABLE_LINES + FIXED_LINES

LINE_LABELS: dict[str, str] = {
    "clinical_labour": "Clinical labour",
    "medical_supplies": "Medical supplies",
    "lab_sendouts": "Lab send-outs",
    "rent": "Rent",
    "it": "IT",
    "admin_staff": "Admin staff",
    "utilities": "Utilities",
}

VISIT_TYPE_LABELS: dict[str, str] = {
    "preventive": "Preventive",
    "sick": "Sick",
    "urgent": "Urgent",
    "procedure": "Procedure",
}

# Standards driver names used in standards.csv.
DRIVER_USD_PER_VISIT = "usd_per_visit"
DRIVER_HOURS_PER_VISIT = "hours_per_visit"
DRIVER_USD_PER_HOUR = "usd_per_hour"
WAGE_VISIT_TYPE = "ALL"

# Materiality gate for commentary.
MATERIAL_USD = 5_000.0
MATERIAL_PCT = 0.10

# A standard further than this from the calibrated estimate is flagged.
CALIBRATION_TOLERANCE = 0.10
