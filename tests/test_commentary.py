from __future__ import annotations

from datetime import date

import pandas as pd

from flexbudget.commentary import commentary, describe, is_material

MARCH = date(2025, 3, 1)


def test_gate_needs_both_dollars_and_percent():
    assert is_material(5_000, 40_000)  # exactly $5,000 and 12.5%
    assert not is_material(4_999, 10_000)  # big percentage, too few dollars
    assert not is_material(20_000, 400_000)  # many dollars, only 5%
    assert is_material(-6_000, 50_000)  # favourable variances count too
    assert not is_material(-6_000, 61_000)  # 9.8% of flexed budget
    assert is_material(-5_000, 0)  # closed clinic: flexed budget of zero


def test_march_2025_flags_every_injected_clinic_line(variance, dataset):
    flagged = {(f.clinic_id, f.line) for f in commentary(variance, MARCH)}
    injected = {(e["clinic"], e["line"]) for e in dataset.truth["active_by_month"]["2025-03"]}
    assert injected <= flagged
    assert injected == {
        ("C07", "clinical_labour"),
        ("C07", "medical_supplies"),
        ("C07", "lab_sendouts"),
        ("C12", "medical_supplies"),
        ("C03", "medical_supplies"),
    }


def test_march_2025_flags_no_clinic_without_an_injected_effect(variance, dataset):
    injected_clinics = {e["clinic"] for e in dataset.truth["active_by_month"]["2025-03"]}
    flagged_clinics = {f.clinic_id for f in commentary(variance, MARCH)}
    assert flagged_clinics == injected_clinics == {"C03", "C07", "C12"}


def test_sentence_names_dominant_component_and_share(variance):
    by_key = {(f.clinic_id, f.line): f for f in commentary(variance, MARCH)}
    c07 = by_key[("C07", "clinical_labour")]
    assert c07.component == "volume"
    assert round(c07.share, 2) == 1.0
    assert c07.sentence.startswith("C07 clinical labour, 2025-03: $")
    assert (
        "unfavourable" in c07.sentence
        and "mainly volume (100% of the gross variance)" in c07.sentence
    )
    c12 = by_key[("C12", "medical_supplies")]
    assert c12.component == "spending"
    assert "(18.0% of flexed budget)" in c12.sentence


def test_commentary_is_deterministic_and_ordered_by_size(variance):
    first, second = commentary(variance, MARCH), commentary(variance, MARCH)
    assert [f.sentence for f in first] == [f.sentence for f in second]
    sizes = [abs(f.total_variance) for f in first]
    assert sizes == sorted(sizes, reverse=True)


def test_closed_clinic_is_flagged_with_a_zero_flexed_budget(variance):
    findings = commentary(variance, date(2025, 2, 1))
    c09 = [f for f in findings if f.clinic_id == "C09"]
    assert {f.line for f in c09} == {"clinical_labour", "medical_supplies", "lab_sendouts"}
    assert all(f.pct_of_flexed is None and "flexed budget of $0" in f.sentence for f in c09)
    assert all(f.component == "volume" for f in c09)


def test_share_stays_between_0_and_100_percent_when_components_offset():
    row = pd.Series(
        {
            "clinic_id": "C99",
            "line": "medical_supplies",
            "month": MARCH,
            "total_variance": 6_000.0,
            "flexed_budget": 40_000.0,
            "volume_variance": -1_000.0,
            "mix_variance": 10_000.0,
            "spending_variance": -3_000.0,
        }
    )
    finding = describe(row)
    assert finding.component == "mix"
    assert finding.share == 10_000 / 14_000  # share of gross movement, not 167% of the net
    assert "mainly mix (71% of the gross variance)" in finding.sentence


def test_every_share_in_every_month_is_a_valid_proportion(variance):
    months = sorted(variance.month.unique())
    shares = [f.share for m in months for f in commentary(variance, m)]
    assert len(shares) > 50
    assert all(0.0 <= s <= 1.0 for s in shares)
