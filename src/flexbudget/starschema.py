"""The star schema written by `export-pbi` and expected by the Power BI model.

Column order here is the CSV header order. Types are the Power BI / TMDL data types.
"""

from __future__ import annotations

TABLES: dict[str, list[tuple[str, str]]] = {
    "FactCost": [
        ("ClinicId", "string"),
        ("Date", "dateTime"),
        ("CostLine", "string"),
        ("ActualCost", "double"),
        ("ActualHours", "double"),
    ],
    "FactVisits": [
        ("ClinicId", "string"),
        ("Date", "dateTime"),
        ("VisitType", "string"),
        ("ActualVisits", "int64"),
    ],
    "FactBudget": [
        ("ClinicId", "string"),
        ("Date", "dateTime"),
        ("CostLine", "string"),
        ("VisitType", "string"),
        ("BudgetVisits", "int64"),
        ("FixedBudget", "double"),
    ],
    "Standards": [
        ("CostLine", "string"),
        ("VisitType", "string"),
        ("UnitCost", "double"),
        ("StdHours", "double"),
        ("StdWageRate", "double"),
    ],
    "FactVariance": [
        ("ClinicId", "string"),
        ("Date", "dateTime"),
        ("CostLine", "string"),
        ("StaticBudget", "double"),
        ("FlexedBudget", "double"),
        ("FlexedBudgetActualMix", "double"),
        ("ActualCost", "double"),
        ("VolumeVariance", "double"),
        ("MixVariance", "double"),
        ("SpendingVariance", "double"),
        ("WageRateVariance", "double"),
        ("EfficiencyVariance", "double"),
        ("TotalVariance", "double"),
    ],
    "DimClinic": [
        ("ClinicId", "string"),
        ("ClinicName", "string"),
        ("ClinicType", "string"),
        ("Region", "string"),
    ],
    "DimDate": [
        ("Date", "dateTime"),
        ("Year", "int64"),
        ("MonthNumber", "int64"),
        ("MonthName", "string"),
        ("YearMonth", "string"),
        ("FiscalYear", "string"),
    ],
    "DimCostLine": [
        ("CostLine", "string"),
        ("CostLineName", "string"),
        ("Behavior", "string"),
        ("SortOrder", "int64"),
    ],
    "DimVisitType": [
        ("VisitType", "string"),
        ("VisitTypeName", "string"),
        ("SortOrder", "int64"),
    ],
}

# (many-side table, column, one-side table, column)
RELATIONSHIPS: list[tuple[str, str, str, str]] = [
    ("FactCost", "ClinicId", "DimClinic", "ClinicId"),
    ("FactCost", "Date", "DimDate", "Date"),
    ("FactCost", "CostLine", "DimCostLine", "CostLine"),
    ("FactVisits", "ClinicId", "DimClinic", "ClinicId"),
    ("FactVisits", "Date", "DimDate", "Date"),
    ("FactVisits", "VisitType", "DimVisitType", "VisitType"),
    ("FactBudget", "ClinicId", "DimClinic", "ClinicId"),
    ("FactBudget", "Date", "DimDate", "Date"),
    ("FactBudget", "CostLine", "DimCostLine", "CostLine"),
    ("FactBudget", "VisitType", "DimVisitType", "VisitType"),
    ("Standards", "CostLine", "DimCostLine", "CostLine"),
    ("Standards", "VisitType", "DimVisitType", "VisitType"),
    ("FactVariance", "ClinicId", "DimClinic", "ClinicId"),
    ("FactVariance", "Date", "DimDate", "Date"),
    ("FactVariance", "CostLine", "DimCostLine", "CostLine"),
]


def header(table: str) -> list[str]:
    return [name for name, _ in TABLES[table]]
