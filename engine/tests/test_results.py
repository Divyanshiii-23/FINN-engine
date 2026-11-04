from pathlib import Path

import pymupdf
import pytest

from finn_engine.extract.results import extract_pdf, quarter_label
from finn_engine.fixtures import results_pdf


@pytest.fixture(scope="module")
def pdf(tmp_path_factory) -> bytes:
    p = tmp_path_factory.mktemp("pdf") / "r.pdf"
    results_pdf(p)
    return p.read_bytes()


def rows(r):
    return {x.key: x for x in r.rows}


def test_picks_consolidated_page_and_converts_lakhs(pdf):
    r = extract_pdf(pdf)
    assert r.status == "ok", r.reason
    assert r.basis == "consolidated" and r.page == 2
    assert r.unit_detected == "lakh"
    assert r.column_order == "header_dates" and r.period_label == "Q2 FY27"
    x = rows(r)
    assert x["revenue"].current.value == 1284.62
    assert x["revenue"].prev_q.value == 1236.04
    assert x["revenue"].prev_y.value == 1151.30
    assert x["pbt"].current.value == 121.48
    assert x["pat"].current.value == 90.06


def test_ebitda_is_computed_with_formula(pdf):
    e = rows(extract_pdf(pdf))["ebitda"]
    assert e.current.value == pytest.approx(121.48 + 14.20 + 52.60 - 8.50)
    assert e.current.evidence.kind == "computed" and "other income" in e.current.evidence.formula


def test_qoq_and_yoy_are_code_computed(pdf):
    x = rows(extract_pdf(pdf))
    assert x["revenue"].qoq == pytest.approx(1284.62 / 1236.04 - 1)
    assert x["revenue"].yoy == pytest.approx(1284.62 / 1151.30 - 1)
    assert x["pat"].qoq == pytest.approx(90.06 / 96.31 - 1)
    assert x["pat"].yoy == pytest.approx(90.06 / 88.02 - 1)


def test_identity_checks_pass_and_are_recorded(pdf):
    r = extract_pdf(pdf)
    ident = [c for c in r.checks if c["check"].startswith("PBT - tax")]
    assert len(ident) == 3 and all(c["ok"] for c in ident)


def test_every_figure_has_evidence(pdf):
    for row in extract_pdf(pdf).rows:
        for f in (row.current, row.prev_q, row.prev_y):
            assert f.value is not None and f.evidence is not None and f.evidence.page == 2


def test_lender_gets_no_ebitda(pdf):
    e = rows(extract_pdf(pdf, is_financial=True))["ebitda"]
    assert e.current.value is None and "not meaningful" in e.label


def test_non_results_pdf_fails_cleanly():
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Intimation of loss of share certificate")
    r = extract_pdf(doc.tobytes())
    assert r.status == "failed" and "no results statement" in r.reason


def test_corrupt_bytes_fail_cleanly():
    r = extract_pdf(b"not a pdf")
    assert r.status == "failed"


def test_missing_rows_need_review():
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((40, 60), "Statement of Consolidated Results (Rs. in crores)")
    p.insert_text((300, 80), "30.09.2026"); p.insert_text((360, 80), "30.06.2026"); p.insert_text((420, 80), "30.09.2025")
    p.insert_text((40, 100), "Revenue from operations"); p.insert_text((300, 100), "100.00"); p.insert_text((360, 100), "90.00"); p.insert_text((420, 100), "80.00")
    p.insert_text((40, 115), "Profit before tax"); p.insert_text((300, 115), "10.00"); p.insert_text((360, 115), "9.00"); p.insert_text((420, 115), "8.00")
    r = extract_pdf(doc.tobytes())
    assert r.status == "needs_review" and "pat" in r.reason


def test_quarter_labels_follow_indian_fiscal_year():
    from datetime import date
    assert quarter_label(date(2026, 9, 30)) == "Q2 FY27"
    assert quarter_label(date(2026, 12, 31)) == "Q3 FY27"
    assert quarter_label(date(2027, 3, 31)) == "Q4 FY27"
    assert quarter_label(date(2026, 6, 30)) == "Q1 FY27"
