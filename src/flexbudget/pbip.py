"""Static validation of the Power BI project against the CSV exports and the metric registry.

Power BI cannot run in CI, so this checks what can be checked from the text files:
  * every `'Table'[Column]` and `[Measure]` reference in a DAX measure resolves;
  * every model column exists in its CSV header with a compatible type;
  * every measure is in `flexbudget.metrics` (and every registered metric is in the model);
  * every field a visual in `report.json` binds to is a real column or measure.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .metrics import METRIC_NAMES
from .tmdl import Model, load_model

STRING_LITERAL = re.compile(r'"(?:[^"]|"")*"')
DAX_REF = re.compile(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_][A-Za-z0-9_]*))?\[([^\]]+)\]")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    tables: int = 0
    columns: int = 0
    measures: int = 0
    relationships: int = 0
    pages: int = 0
    visuals: int = 0
    bindings: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        status = "PASS" if self.ok else f"FAIL ({len(self.errors)} errors)"
        return (
            f"validate-pbi: {status}: {self.tables} tables, {self.columns} columns, "
            f"{self.measures} measures, {self.relationships} relationships, "
            f"{self.pages} pages, {self.visuals} visuals, {self.bindings} field bindings"
        )


def dax_references(expression: str) -> list[tuple[str | None, str]]:
    """(table, name) pairs for every bracketed reference; table is None for `[Measure]`."""
    stripped = STRING_LITERAL.sub('""', expression)
    refs = []
    for match in DAX_REF.finditer(stripped):
        table = match.group(1).replace("''", "'") if match.group(1) else match.group(2)
        refs.append((table, match.group(3)))
    return refs


def _check_measures(model: Model, report: Report) -> None:
    measure_names = {m.name for m in model.measures()}
    for measure in model.measures():
        for table, name in dax_references(measure.expression):
            if table is None:
                if name not in measure_names:
                    report.errors.append(
                        f"measure '{measure.name}': [{name}] is not a measure in the model"
                    )
                continue
            owner = model.tables.get(table)
            if owner is None:
                report.errors.append(
                    f"measure '{measure.name}': table '{table}' in '{table}'[{name}] does not exist"
                )
            elif name not in {c.name for c in owner.columns} | {m.name for m in owner.measures}:
                report.errors.append(
                    f"measure '{measure.name}': column '{table}'[{name}] does not exist"
                )


def _type_ok(data_type: str, values: list[str]) -> bool:
    if data_type == "string":
        return True
    try:
        if data_type == "int64":
            return all(re.fullmatch(r"-?\d+", v) for v in values)
        if data_type in ("double", "decimal"):
            return all(float(v) == float(v) for v in values)
        if data_type == "dateTime":
            for v in values:
                try:
                    date.fromisoformat(v)
                except ValueError:
                    datetime.fromisoformat(v)
            return True
        if data_type == "boolean":
            return all(v.lower() in ("true", "false") for v in values)
    except ValueError:
        return False
    return False


def _check_columns(model: Model, data_dir: Path, report: Report) -> None:
    for table in model.tables.values():
        if not table.has_partition:
            continue
        path = data_dir / f"{table.name}.csv"
        if not path.exists():
            report.errors.append(f"table '{table.name}': CSV {path.name} not found in {data_dir}")
            continue
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            rows = list(reader)
        for column in table.columns:
            source = column.source_column or column.name
            if source not in header:
                report.errors.append(
                    f"column '{table.name}'[{column.name}]: sourceColumn '{source}' "
                    f"is not in the header of {path.name}"
                )
                continue
            values = [r[source] for r in rows if r[source] not in ("", None)]
            if not _type_ok(column.data_type, values):
                report.errors.append(
                    f"column '{table.name}'[{column.name}]: values in {path.name} "
                    f"are not valid {column.data_type}"
                )


def _check_query_groups(model: Model, report: Report) -> None:
    for file, group in model.query_group_refs:
        if group not in model.query_groups:
            report.errors.append(f"{file}: queryGroup '{group}' is referenced but never defined")


def _check_registry(model: Model, report: Report) -> None:
    names = {m.name for m in model.measures()}
    for name in sorted(names - METRIC_NAMES):
        report.errors.append(f"measure '{name}' is not in the metric registry")
    for name in sorted(METRIC_NAMES - names):
        report.errors.append(f"registered metric '{name}' has no measure in the model")


def _check_relationships(model: Model, report: Report) -> None:
    for rel in model.relationships:
        for table, column in ((rel.from_table, rel.from_column), (rel.to_table, rel.to_column)):
            owner = model.tables.get(table)
            if owner is None or column not in {c.name for c in owner.columns}:
                report.errors.append(f"relationship refers to missing column '{table}'[{column}]")


def _check_report(model: Model, report_path: Path, report: Report) -> None:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    measures = {(m.table, m.name) for m in model.measures()}
    measure_names = {m.name for m in model.measures()}
    for section in data.get("sections", []):
        report.pages += 1
        page = section.get("displayName", section.get("name", "?"))
        for container in section.get("visualContainers", []):
            report.visuals += 1
            config = json.loads(container["config"])
            visual = config.get("singleVisual", {})
            query = visual.get("prototypeQuery", {})
            aliases = {f["Name"]: f["Entity"] for f in query.get("From", [])}
            select_names = set()
            for item in query.get("Select", []):
                report.bindings += 1
                select_names.add(item.get("Name"))
                kind = "Measure" if "Measure" in item else "Column"
                body = item.get(kind)
                if body is None:
                    report.errors.append(f"page '{page}': unsupported select item {item}")
                    continue
                entity = aliases.get(body["Expression"]["SourceRef"]["Source"])
                prop = body["Property"]
                owner = model.tables.get(entity or "")
                if owner is None:
                    report.errors.append(
                        f"page '{page}' visual '{config.get('name')}': entity '{entity}' "
                        "does not exist"
                    )
                elif kind == "Measure":
                    if (entity, prop) not in measures and prop not in measure_names:
                        report.errors.append(
                            f"page '{page}' visual '{config.get('name')}': "
                            f"measure '{prop}' does not exist"
                        )
                elif prop not in {c.name for c in owner.columns}:
                    report.errors.append(
                        f"page '{page}' visual '{config.get('name')}': "
                        f"column '{entity}'[{prop}] does not exist"
                    )
            for role, refs in visual.get("projections", {}).items():
                for ref in refs:
                    if ref["queryRef"] not in select_names:
                        report.errors.append(
                            f"page '{page}' visual '{config.get('name')}': "
                            f"projection {role} uses '{ref['queryRef']}' which is not selected"
                        )


def validate_project(project_dir: str | Path, data_dir: str | Path | None = None) -> Report:
    """Validate a PBIP folder (containing *.SemanticModel and *.Report) and its CSV data."""
    project = Path(project_dir)
    report = Report()
    models = sorted(project.glob("*.SemanticModel"))
    reports = sorted(project.glob("*.Report"))
    if not models or not reports:
        report.errors.append(f"{project}: expected a *.SemanticModel and a *.Report folder")
        return report
    definition = models[0] / "definition"
    model = load_model(definition)
    report.tables = len(model.tables)
    report.columns = sum(len(t.columns) for t in model.tables.values())
    report.measures = len(model.measures())
    report.relationships = len(model.relationships)
    _check_measures(model, report)
    _check_columns(model, Path(data_dir) if data_dir else project / "data", report)
    _check_registry(model, report)
    _check_query_groups(model, report)
    _check_relationships(model, report)
    report_json = reports[0] / "report.json"
    if report_json.exists():
        _check_report(model, report_json, report)
    else:
        report.errors.append(f"{report_json} not found")
    return report
