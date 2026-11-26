from __future__ import annotations

import json
from pathlib import Path

from flexbudget.metrics import ENGINE_COLUMNS, METRIC_NAMES, METRICS, by_name
from flexbudget.pbip import dax_references, validate_project
from flexbudget.tmdl import load_model, parse_table

REPO = Path(__file__).resolve().parents[1]
DEFINITION = "FlexBudget.SemanticModel/definition"


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_shipped_project_passes():
    report = validate_project(REPO / "powerbi")
    assert report.errors == []
    assert report.ok
    assert (report.tables, report.measures, report.relationships) == (9, 14, 15)
    assert report.pages == 3 and report.visuals > 10 and report.bindings > 30
    assert "PASS" in report.summary()


def test_model_declares_the_brief_measures_and_the_data_folder_parameter():
    model = load_model(REPO / "powerbi" / DEFINITION)
    names = {m.name for m in model.measures()}
    for needed in (
        "Actual Cost",
        "Static Budget",
        "Flexed Budget",
        "Volume Variance",
        "Mix Variance",
        "Spending Variance",
        "Wage Rate Variance",
        "Efficiency Variance",
        "Total Variance",
        "Variance Pct",
    ):
        assert needed in names
    assert model.expressions == ["DataFolder"]
    assert all(t.has_partition for t in model.tables.values())
    partition = (REPO / "powerbi" / DEFINITION / "tables" / "FactCost.tmdl").read_text()
    assert "DataFolder" in partition


def test_report_has_the_three_pages():
    data = json.loads((REPO / "powerbi/FlexBudget.Report/report.json").read_text())
    assert [s["displayName"] for s in data["sections"]] == [
        "Network overview",
        "Clinic drill",
        "Labour",
    ]


def test_measure_referencing_a_missing_column_fails_naming_measure_and_column(project_copy):
    _edit(
        project_copy / DEFINITION / "tables/FactCost.tmdl",
        "SUM(FactCost[ActualCost])",
        "SUM(FactCost[ActualCostTypo])",
    )
    report = validate_project(project_copy)
    assert not report.ok
    assert any("'Actual Cost'" in e and "'FactCost'[ActualCostTypo]" in e for e in report.errors)


def test_measure_referencing_a_missing_measure_or_table_fails(project_copy):
    path = project_copy / DEFINITION / "tables/FactCost.tmdl"
    _edit(path, "[Flexed Budget] - [Static Budget]", "[Flexed Budget] - [Nonexistent Measure]")
    _edit(path, "SUM(FactVisits[ActualVisits])", "SUM(FactVisitz[ActualVisits])")
    errors = validate_project(project_copy).errors
    assert any("'Volume Variance'" in e and "[Nonexistent Measure]" in e for e in errors)
    assert any("'Actual Visits'" in e and "FactVisitz" in e for e in errors)


def test_measure_missing_from_the_registry_fails(project_copy):
    path = project_copy / DEFINITION / "tables/FactCost.tmdl"
    _edit(path, "\tmeasure 'Total Variance' =", "\tmeasure 'Grand Variance' =")
    errors = validate_project(project_copy).errors
    assert any("'Grand Variance' is not in the metric registry" in e for e in errors)
    assert any("registered metric 'Total Variance'" in e for e in errors)


def test_column_missing_from_the_csv_header_fails(project_copy):
    csv_path = project_copy / "data" / "DimClinic.csv"
    lines = csv_path.read_text().splitlines()
    lines[0] = lines[0].replace("Region", "Territory")
    csv_path.write_text("\n".join(lines) + "\n")
    errors = validate_project(project_copy).errors
    assert any("'DimClinic'[Region]" in e and "not in the header" in e for e in errors)


def test_incompatible_column_type_fails(project_copy):
    _edit(
        project_copy / DEFINITION / "tables/FactVisits.tmdl",
        "column ClinicId\n\t\tdataType: string",
        "column ClinicId\n\t\tdataType: int64",
    )
    errors = validate_project(project_copy).errors
    assert any("'FactVisits'[ClinicId]" in e and "int64" in e for e in errors)


def test_visual_bound_to_a_missing_field_fails(project_copy):
    path = project_copy / "FlexBudget.Report/report.json"
    text = path.read_text()
    assert "Volume Variance" in text
    path.write_text(text.replace("Volume Variance", "Volume Varience"))
    errors = validate_project(project_copy).errors
    assert any("measure 'Volume Varience' does not exist" in e for e in errors)


def test_visual_bound_to_a_missing_column_fails(project_copy):
    path = project_copy / "FlexBudget.Report/report.json"
    path.write_text(
        path.read_text().replace('\\"Property\\":\\"ClinicName\\"', '\\"Property\\":\\"Clinic\\"')
    )
    errors = validate_project(project_copy).errors
    assert any("'DimClinic'[Clinic] does not exist" in e for e in errors)


def test_missing_project_folders_are_reported(tmp_path):
    assert not validate_project(tmp_path).ok


def test_dax_reference_parser_ignores_strings_and_handles_quoted_tables():
    refs = dax_references(
        "CALCULATE(SUM('Fact Cost'[Amount]), Dim[Line] = \"x[Fake]\") + [Other Measure]"
    )
    assert refs == [("Fact Cost", "Amount"), ("Dim", "Line"), (None, "Other Measure")]


def test_tmdl_parser_reads_multiline_measures_and_columns():
    text = (
        "table T\n\tlineageTag: x\n\n\tmeasure 'A B' =\n\t\t\tSUM(T[C])\n\t\t\t\t+ 1\n"
        "\t\tformatString: 0\n\n\tcolumn C\n\t\tdataType: int64\n\t\tsourceColumn: C\n\n"
        "\tpartition T = m\n\t\tmode: import\n"
    )
    table = parse_table(text)
    assert table.measures[0].name == "A B"
    assert table.measures[0].expression == "SUM(T[C])\n+ 1"
    assert (table.columns[0].name, table.columns[0].data_type) == ("C", "int64")
    assert table.has_partition


def test_registry_is_consistent():
    assert len(METRIC_NAMES) == len(METRICS)
    assert len(set(ENGINE_COLUMNS)) == len(ENGINE_COLUMNS)
    assert by_name("Variance Pct").kind == "ratio"
