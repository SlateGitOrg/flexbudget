"""A small parser for the subset of TMDL the semantic model uses: tables, columns, measures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROPERTY_LINE = re.compile(
    r"^\t\t(formatString|lineageTag|displayFolder|description|isHidden|dataCategory|"
    r"annotation|changedProperty)\b"
)


@dataclass
class Column:
    name: str
    data_type: str = ""
    source_column: str = ""


@dataclass
class Measure:
    name: str
    expression: str
    table: str


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    has_partition: bool = False


@dataclass
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class Model:
    tables: dict[str, Table] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    expressions: list[str] = field(default_factory=list)

    def measures(self) -> list[Measure]:
        return [m for t in self.tables.values() for m in t.measures]


def unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def _split_ref(text: str) -> tuple[str, str]:
    table, _, column = text.partition(".")
    return unquote(table), unquote(column)


def parse_table(text: str) -> Table:
    lines = text.splitlines()
    table: Table | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("table "):
            table = Table(unquote(line[len("table ") :]))
        elif table is not None and line.startswith("\tcolumn "):
            column = Column(unquote(line[len("\tcolumn ") :].split("=")[0]))
            table.columns.append(column)
            i += 1
            while i < len(lines) and lines[i].startswith("\t\t"):
                prop = lines[i].strip()
                if prop.startswith("dataType:"):
                    column.data_type = prop.split(":", 1)[1].strip()
                elif prop.startswith("sourceColumn:"):
                    column.source_column = prop.split(":", 1)[1].strip()
                i += 1
            continue
        elif table is not None and line.startswith("\tmeasure "):
            head = line[len("\tmeasure ") :]
            name_part, _, first = head.partition(" =")
            expression = [first.strip()] if first.strip() else []
            i += 1
            while (
                i < len(lines) and lines[i].startswith("\t\t") and not PROPERTY_LINE.match(lines[i])
            ):
                expression.append(lines[i].strip())
                i += 1
            table.measures.append(Measure(unquote(name_part), "\n".join(expression), table.name))
            continue
        elif table is not None and line.startswith("\tpartition "):
            table.has_partition = True
        i += 1
    if table is None:
        raise ValueError("no 'table' declaration found")
    return table


def parse_relationships(text: str) -> list[Relationship]:
    out: list[Relationship] = []
    current: dict[str, str] = {}
    for line in text.splitlines() + ["relationship end"]:
        if line.startswith("relationship "):
            if "fromColumn" in current and "toColumn" in current:
                f_table, f_col = _split_ref(current["fromColumn"])
                t_table, t_col = _split_ref(current["toColumn"])
                out.append(Relationship(f_table, f_col, t_table, t_col))
            current = {}
        elif ":" in line:
            key, _, value = line.strip().partition(":")
            current[key] = value.strip()
    return out


def load_model(definition_dir: Path) -> Model:
    model = Model()
    for path in sorted((definition_dir / "tables").glob("*.tmdl")):
        table = parse_table(path.read_text(encoding="utf-8"))
        model.tables[table.name] = table
    rel_path = definition_dir / "relationships.tmdl"
    if rel_path.exists():
        model.relationships = parse_relationships(rel_path.read_text(encoding="utf-8"))
    expr_path = definition_dir / "expressions.tmdl"
    if expr_path.exists():
        for line in expr_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("expression "):
                model.expressions.append(unquote(line[len("expression ") :].split("=")[0]))
    return model
