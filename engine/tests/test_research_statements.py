"""Statement parsing for layouts the synthetic companies don't cover.

Banks file under the Banking Regulation Act (Third Schedule): "Interest earned",
"Interest expended", "Provisions (other than tax) and contingencies", and a
balance sheet of "Capital and liabilities" / "Assets" with "Advances" and a bare
"Total" on each side. Dashes in figure columns mean zero.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from finn_engine.research import statements as S
from finn_engine.research.fixtures import Pdf, _columns, _table


def _pdf_bytes(build) -> bytes:
    pdf = Pdf(rupee=False)
    build(pdf)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.pdf"
        pdf.save(p)
        return p.read_bytes()


def _bank(pdf: Pdf) -> None:
    cols = _columns("Q2 FY27")
    dates, caps = [d for _, d, _ in cols], [c for _, _, c in cols]
    p = pdf.page(landscape=True)
    pdf.text(p, (36, 44), "Example Bank Limited", 11)
    pdf.text(p, (36, 60), "Statement of Unaudited Standalone Financial Results for the quarter ended 30 September 2026", 9)
    pdf.text(p, (36, 74), "(Rs. in crore)", 7.5)
    rows = [
        ("1", "Interest earned (a)+(b)+(c)+(d)", ["12,000.00", "11,800.00", "11,000.00", "23,800.00", "21,700.00", "44,500.00"]),
        ("(a)", "  Interest/discount on advances/bills", ["9,000.00", "8,900.00", "8,200.00", "17,900.00", "16,200.00", "33,300.00"]),
        ("2", "Other income", ["1,500.00", "1,400.00", "1,300.00", "2,900.00", "2,600.00", "5,400.00"]),
        ("3", "Total income (1+2)", ["13,500.00", "13,200.00", "12,300.00", "26,700.00", "24,300.00", "49,900.00"]),
        ("4", "Interest expended", ["7,000.00", "6,900.00", "6,500.00", "13,900.00", "12,900.00", "26,300.00"]),
        ("5", "Operating expenses (i)+(ii)", ["3,000.00", "2,950.00", "2,800.00", "5,950.00", "5,600.00", "11,500.00"]),
        ("6", "Operating profit before provisions and contingencies", ["3,500.00", "3,350.00", "3,000.00", "6,850.00", "5,800.00", "12,100.00"]),
        ("7", "Provisions (other than tax) and contingencies", ["400.00", "380.00", "350.00", "780.00", "700.00", "1,450.00"]),
        ("8", "Exceptional items", ["-", "-", "-", "-", "-", "-"]),
        ("9", "Profit from ordinary activities before tax", ["3,100.00", "2,970.00", "2,650.00", "6,070.00", "5,100.00", "10,650.00"]),
        ("10", "Tax expense", ["780.00", "750.00", "670.00", "1,530.00", "1,290.00", "2,690.00"]),
        ("11", "Net profit for the period", ["2,320.00", "2,220.00", "1,980.00", "4,540.00", "3,810.00", "7,960.00"]),
    ]
    _table(pdf, p, 100, caps, dates, rows)

    b = pdf.page()
    pdf.text(b, (36, 44), "Example Bank Limited", 11)
    pdf.text(b, (36, 60), "Standalone Statement of Assets and Liabilities", 9)
    pdf.text(b, (36, 74), "(Rs. in crore)", 7.5)
    _table(pdf, b, 100, ["As at", "As at"], ["30.09.2026", "31.03.2026"], [
        ("", "Capital and Liabilities", []),
        ("", "Capital", ["760.00", "760.00"]),
        ("", "Reserves and surplus", ["60,000.00", "57,000.00"]),
        ("", "Deposits", ["5,00,000.00", "4,80,000.00"]),
        ("", "Borrowings", ["40,000.00", "42,000.00"]),
        ("", "Other liabilities and provisions", ["19,240.00", "18,240.00"]),
        ("", "Total", ["6,20,000.00", "5,98,000.00"]),
        ("", "Assets", []),
        ("", "Cash and balances with Reserve Bank of India", ["25,000.00", "24,000.00"]),
        ("", "Balances with banks and money at call and short notice", ["10,000.00", "9,000.00"]),
        ("", "Investments", ["1,50,000.00", "1,45,000.00"]),
        ("", "Advances", ["4,00,000.00", "3,85,000.00"]),
        ("", "Fixed assets", ["5,000.00", "5,000.00"]),
        ("", "Other assets", ["30,000.00", "30,000.00"]),
        ("", "Total", ["6,20,000.00", "5,98,000.00"]),
    ], x0=380, step=100)


def test_bank_format_is_read():
    st = S.parse(_pdf_bytes(_bank), is_financial=True)
    assert st.status != "failed", st.reason
    q = st.pnl["Q2 FY27"]
    assert q["revenue"].value == 12000 and q["finance_cost"].value == 7000
    assert q["impairment"].value == 400 and q["pat"].value == 2320 and q["other_income"].value == 1500
    assert q["exceptional"].value == 0  # a dash is zero, not missing
    bs = st.bs["Sep 2026"] if "Sep 2026" in st.bs else next(iter(st.bs.values()))
    assert bs["loans"].value == 400000
    assert bs["borrowings"].value == 540000  # deposits + borrowings
    assert bs["cash"].value == 25000 and bs["bank_balances"].value == 10000
    assert any(c["ok"] for c in st.checks if c["check"].startswith("Total assets"))


def _corporate_with_dash(pdf: Pdf) -> None:
    cols = _columns("Q2 FY27")
    dates, caps = [d for _, d, _ in cols], [c for _, _, c in cols]
    p = pdf.page(landscape=True)
    pdf.text(p, (36, 44), "Example Industries Limited", 11)
    pdf.text(p, (36, 60), "Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026", 9)
    pdf.text(p, (36, 74), "(Rs. in crore)", 7.5)
    v = lambda x: [x] * 6  # noqa: E731
    _table(pdf, p, 100, caps, dates, [
        ("1", "Revenue from operations", v("1,000.00")),
        ("2", "Other income", v("-")),
        ("3", "Total income (1+2)", v("1,000.00")),
        ("4", "Expenses", []),
        ("(a)", "  Cost of materials consumed", v("500.00")),
        ("(b)", "  Employee benefits expense", v("100.00")),
        ("(c)", "  Finance costs", v("Nil")),
        ("(d)", "  Depreciation and amortisation expense", v("50.00")),
        ("(e)", "  Other expenses", v("150.00")),
        ("", "Total expenses", v("800.00")),
        ("5", "Profit before exceptional items and tax", v("200.00")),
        ("6", "Exceptional items", v("-")),
        ("7", "Profit before tax", v("200.00")),
        ("8", "Total tax expense", v("50.00")),
        ("9", "Net profit for the period", v("150.00")),
    ])


def test_dash_and_nil_cells_are_zero():
    st = S.parse(_pdf_bytes(_corporate_with_dash), is_financial=False)
    q = st.pnl["Q2 FY27"]
    assert q["other_income"].value == 0 and q["finance_cost"].value == 0 and q["exceptional"].value == 0


def _corporate(exceptional: str, pre_line: bool):
    def build(pdf: Pdf) -> None:
        cols = _columns("Q2 FY27")
        dates, caps = [d for _, d, _ in cols], [c for _, _, c in cols]
        p = pdf.page(landscape=True)
        pdf.text(p, (36, 44), "Example Industries Limited", 11)
        pdf.text(p, (36, 60), "Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026", 9)
        pdf.text(p, (36, 74), "(Rs. in crore)", 7.5)
        v = lambda x: [x] * 6  # noqa: E731
        pbt = "180.00" if exceptional != "-" else "200.00"
        rows = [("1", "Revenue from operations", v("1,000.00")), ("2", "Other income", v("10.00")), ("3", "Total income (1+2)", v("1,010.00")),
                ("4", "Expenses", []), ("(a)", "  Cost of materials consumed", v("500.00")), ("(b)", "  Finance costs", v("20.00")),
                ("(c)", "  Depreciation and amortisation expense", v("50.00")), ("(d)", "  Other expenses", v("240.00")), ("", "Total expenses", v("810.00"))]
        if pre_line:
            rows.append(("5", "Profit before exceptional items and tax", v("200.00")))
        rows += [("6", "Exceptional items", v(exceptional)), ("7", "Profit before tax", v(pbt)), ("8", "Total tax expense", v("45.00")), ("9", "Net profit for the period", v("135.00"))]
        _table(pdf, p, 100, caps, dates, rows)
    return build


def _ebitda(build):
    from finn_engine.research.financials import Facts, Numbers
    from finn_engine.research.models import Doc
    st = S.parse(_pdf_bytes(build), is_financial=False)
    doc = Doc(id="d:test", kind="results", title="Results Q2 FY27", period="Q2 FY27", source="bse", status="parsed")
    n = Numbers.build(Facts(), [(doc, st)], is_financial=False)
    return n.ebitda("Q2 FY27"), n


def test_ebitda_never_includes_exceptional_items():
    e, _ = _ebitda(_corporate("20.00", pre_line=True))
    assert e and e.value == 260.0  # 200 + 20 + 50 - 10, from the pre-exceptional line
    e, n = _ebitda(_corporate("20.00", pre_line=False))
    assert e is None  # PBT carries a non-zero exceptional item and no pre-exceptional line: not computed
    e, n = _ebitda(_corporate("-", pre_line=False))
    assert e and e.value == 260.0 and "no exceptional items" in n.facts.items[e.fact].formula
