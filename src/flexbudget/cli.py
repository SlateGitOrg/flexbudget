"""Command line interface: generate, calibrate, variance, commentary, export-pbi, validate-pbi."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import typer

from .calibrate import calibrate as run_calibrate
from .commentary import commentary as run_commentary
from .constants import LINE_LABELS
from .dates import label, parse_month
from .engine import rollup, run_engine
from .export import export_star
from .generate import generate as run_generate
from .generate import write_dataset
from .inputs import InputError, load_inputs
from .pbip import validate_project

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Flexible-budget variance for an outpatient clinic network.",
)

DataOption = typer.Option("data", "--data", help="Folder written by `generate`.")


def _month(text: str) -> date:
    try:
        return parse_month(text)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _load(data: Path):
    try:
        return load_inputs(data)
    except InputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _money(value: float) -> str:
    return "" if pd.isna(value) else f"{value:,.0f}"


@app.command()
def generate(
    seed: int = typer.Option(7, help="Seed for the deterministic generator."),
    out: Path = typer.Option(Path("data"), help="Output folder."),
) -> None:
    """Write the synthetic clinic-network inputs and truth.json."""
    paths = write_dataset(run_generate(seed), out)
    typer.echo(f"wrote {len(paths)} files to {out}")


@app.command()
def calibrate(
    data: Path = DataOption,
    tolerance: float = typer.Option(
        0.10, help="Flag standards further than this from the estimate."
    ),
) -> None:
    """Estimate cost per visit type from the first year and flag standards that are off."""
    table = run_calibrate(_load(data), tolerance)
    rows = []
    for r in table.itertuples():
        rows.append(
            {
                "line": r.line,
                "visit_type": r.visit_type,
                "standard": f"{r.standard:,.2f}",
                "estimate": f"{r.estimate:,.2f}",
                "std_error": f"{r.std_error:,.2f}",
                "gap": f"{r.gap:+.1%}",
                "flag": "STANDARD OFF" if r.flag else "",
            }
        )
    typer.echo(pd.DataFrame(rows).to_string(index=False))


@app.command()
def variance(
    month: str = typer.Option(..., help="Month as YYYY-MM."),
    data: Path = DataOption,
    clinics: str = typer.Option("", help="Comma-separated clinic ids; default all."),
    by: str = typer.Option("clinic", help="Roll up by 'clinic' or 'line'."),
) -> None:
    """Static, flexed and actual cost with the volume, mix and spending split for one month."""
    when = _month(month)
    result = run_engine(_load(data))
    result = result[result["month"] == when]
    if clinics:
        result = result[result["clinic_id"].isin([c.strip() for c in clinics.split(",")])]
    if result.empty:
        typer.echo(f"no rows for {label(when)}", err=True)
        raise typer.Exit(code=1)
    key = "clinic_id" if by == "clinic" else "line"
    table = rollup(result, [key])
    shown = table[
        [
            key,
            "static_budget",
            "flexed_budget",
            "actual_cost",
            "volume_variance",
            "mix_variance",
            "spending_variance",
            "total_variance",
        ]
    ].copy()
    shown.columns = ["clinic" if by == "clinic" else "line", *shown.columns[1:]]
    for col in shown.columns[1:]:
        shown[col] = shown[col].map(_money)
    if by != "clinic":
        shown["line"] = shown["line"].map(LINE_LABELS)
    typer.echo(f"{label(when)}  (USD, positive = unfavourable)")
    typer.echo(shown.to_string(index=False))


@app.command()
def commentary(
    month: str = typer.Option(..., help="Month as YYYY-MM."),
    data: Path = DataOption,
) -> None:
    """One sentence per clinic-line whose variance passes the materiality gate."""
    when = _month(month)
    findings = run_commentary(run_engine(_load(data)), when)
    if not findings:
        typer.echo(f"{label(when)}: no clinic-line passes the materiality gate")
        return
    for finding in findings:
        typer.echo(finding.sentence)


@app.command("export-pbi")
def export_pbi(
    data: Path = DataOption,
    out: Path = typer.Option(Path("powerbi/data"), help="Folder for the star-schema CSVs."),
) -> None:
    """Write the star schema the Power BI model loads."""
    paths = export_star(_load(data), out)
    typer.echo(f"wrote {len(paths)} tables to {out}")


@app.command("validate-pbi")
def validate_pbi(
    project: Path = typer.Option(Path("powerbi"), help="Folder holding the PBIP project."),
    data: Path | None = typer.Option(None, help="CSV folder; default <project>/data."),
) -> None:
    """Check the TMDL model and report against the CSVs and the metric registry."""
    report = validate_project(project, data)
    for error in report.errors:
        typer.echo(f"  - {error}")
    typer.echo(report.summary())
    if not report.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
