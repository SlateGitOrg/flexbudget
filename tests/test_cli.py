from __future__ import annotations

import json

from typer.testing import CliRunner

from flexbudget.cli import app

runner = CliRunner()


def test_generate_writes_the_input_files(tmp_path):
    result = runner.invoke(app, ["generate", "--seed", "7", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "wrote 8 files" in result.output
    assert json.loads((tmp_path / "truth.json").read_text())["seed"] == 7
    assert (tmp_path / "actual_cost.csv").exists()


def test_variance_prints_a_table_for_selected_clinics(data_dir):
    result = runner.invoke(
        app, ["variance", "--data", str(data_dir), "--month", "2025-03", "--clinics", "C07,C12"]
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("2025-03")
    assert "volume_variance" in lines[1] and "total_variance" in lines[1]
    assert [ln.split()[0] for ln in lines[2:]] == ["C07", "C12"]


def test_variance_by_line_uses_readable_names(data_dir):
    result = runner.invoke(
        app, ["variance", "--data", str(data_dir), "--month", "2025-03", "--by", "line"]
    )
    assert result.exit_code == 0
    assert "Clinical labour" in result.output and "Rent" in result.output


def test_variance_rejects_bad_month_and_empty_month(data_dir):
    bad = runner.invoke(app, ["variance", "--data", str(data_dir), "--month", "2025-13"])
    assert bad.exit_code != 0
    empty = runner.invoke(app, ["variance", "--data", str(data_dir), "--month", "2030-01"])
    assert empty.exit_code == 1


def test_commentary_prints_one_sentence_per_flagged_line(data_dir):
    result = runner.invoke(app, ["commentary", "--data", str(data_dir), "--month", "2025-03"])
    assert result.exit_code == 0
    sentences = result.output.strip().splitlines()
    assert len(sentences) == 5
    assert all(s.endswith("of the gross variance).") for s in sentences)
    quiet = runner.invoke(app, ["commentary", "--data", str(data_dir), "--month", "2023-08"])
    assert quiet.exit_code == 0


def test_calibrate_marks_the_urgent_supply_standard(data_dir):
    result = runner.invoke(app, ["calibrate", "--data", str(data_dir)])
    assert result.exit_code == 0
    flagged = [ln for ln in result.output.splitlines() if "STANDARD OFF" in ln]
    assert len(flagged) == 1 and "medical_supplies" in flagged[0] and "urgent" in flagged[0]


def test_export_then_validate_round_trip(data_dir, tmp_path, project_copy):
    out = tmp_path / "star"
    exported = runner.invoke(app, ["export-pbi", "--data", str(data_dir), "--out", str(out)])
    assert exported.exit_code == 0 and "wrote 9 tables" in exported.output
    ok = runner.invoke(app, ["validate-pbi", "--project", str(project_copy), "--data", str(out)])
    assert ok.exit_code == 0, ok.output
    assert "PASS" in ok.output


def test_validate_pbi_exits_1_and_names_the_problem(project_copy):
    path = project_copy / "FlexBudget.SemanticModel/definition/tables/FactCost.tmdl"
    path.write_text(path.read_text().replace("FactCost[ActualCost]", "FactCost[Nope]", 1))
    result = runner.invoke(app, ["validate-pbi", "--project", str(project_copy)])
    assert result.exit_code == 1
    assert "'Actual Cost'" in result.output and "Nope" in result.output
    assert "FAIL" in result.output


def test_missing_data_folder_exits_2(tmp_path):
    result = runner.invoke(app, ["variance", "--data", str(tmp_path), "--month", "2025-03"])
    assert result.exit_code == 2
