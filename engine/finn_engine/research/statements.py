"""Statements filed with quarterly results (SEBI LODR Reg. 33).

A results filing carries the P&L for three quarters plus year-to-date and
full-year columns. With the half-year (Q2) and annual (Q4) results it also
carries the statement of assets and liabilities and the cash flow statement.
This module reads all of them from the PDF text layer, without a model.

Columns are identified by the dates printed in the header row, never by
position alone: the first three dates must be this quarter, the preceding
quarter and the same quarter last year; a later date equal to this quarter's
end is the year-to-date column; a March date is a full-year column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pymupdf

from ..extract.results import DATE, SERIAL, Row, _unit, rows_from_page
from . import periods as P


@dataclass
class Cell:
    value: float
    page: int
    row_text: str
    column: str  # header date as printed, e.g. "30.09.2026"
    statement: str  # "P&L" | "Balance sheet" | "Cash flow" | "Segment note"
    basis: str


@dataclass
class Statements:
    pnl: dict[str, dict[str, Cell]] = field(default_factory=dict)  # period label -> field -> cell
    bs: dict[str, dict[str, Cell]] = field(default_factory=dict)  # "as at" period label (e.g. "H1 FY27", "FY26") -> field
    cf: dict[str, dict[str, Cell]] = field(default_factory=dict)  # period label -> field
    segments: dict[str, dict[str, Cell]] = field(default_factory=dict)  # quarter label -> segment name -> cell
    basis: dict[str, str] = field(default_factory=dict)  # statement -> consolidated/standalone
    unit: str | None = None
    current: str | None = None  # quarter this filing reports
    checks: list[dict] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)  # printed labels of itemised lines without a fixed key
    status: str = "ok"
    reason: str | None = None


# ---------------------------------------------------------------- columns

def _date_columns(page: pymupdf.Page, min_dates: int) -> list[tuple[float, date, str]]:
    by_line: dict[int, list[tuple[float, date, str]]] = {}
    for w in page.get_text("words"):
        m = DATE.search(w[4])
        if not m:
            continue
        try:
            dt = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        by_line.setdefault(int(round(((w[1] + w[3]) / 2) / 4)), []).append(((w[0] + w[2]) / 2, dt, m.group(0)))
    best = max(by_line.values(), key=len, default=[])
    return sorted(best, key=lambda t: t[0]) if len(best) >= min_dates else []


def _months(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def pnl_labels(cols: list[tuple[float, date, str]]) -> list[str | None] | None:
    """Period label per P&L column, or None if the header doesn't validate."""
    if len(cols) < 3:
        return None
    d0, d1, d2 = cols[0][1], cols[1][1], cols[2][1]
    if not (2 <= _months(d0, d1) <= 4 and 11 <= _months(d0, d2) <= 13):
        return None
    out: list[str | None] = [P.label_for_end(d0), P.label_for_end(d1), P.label_for_end(d2)]
    for _, d, _ in cols[3:]:
        if d in (d0, d2):
            out.append(P.label_for_end(d, "ytd"))
        elif d.month == 3:
            out.append(P.label_for_end(d, "year"))
        else:
            out.append(None)
    return out


def _bs_label(d: date) -> str | None:
    # Balance sheets are "as at" a date; label by the period that ends there.
    return P.label_for_end(d, "ytd")


def _assign(row: Row, cols: list[tuple[float, date, str]]) -> list[float | None]:
    out: list[float | None] = [None] * len(cols)
    for xc, v in row.numbers:
        i = min(range(len(cols)), key=lambda k: abs(cols[k][0] - xc))
        if abs(cols[i][0] - xc) < 60:
            out[i] = v
    return out


# ---------------------------------------------------------------- row maps

PNL_FIELDS: list[tuple[str, str, str | None]] = [
    ("revenue", r"^(total )?(revenue from operations|income from operations|net sales|interest earned)", r"other|segment"),
    ("interest_income", r"^interest income", None),
    ("other_income", r"^other income", r"comprehensive"),
    ("total_income", r"^total income", r"comprehensive"),
    ("materials", r"^cost of (raw )?materials? consumed", None),
    ("purchases", r"^purchases? of stock", None),
    ("inventory_change", r"^changes? in inventor", None),
    ("employee", r"^employee", None),
    # Banks file in the Banking Regulation Act format: "Interest expended", "Provisions (other than tax) and contingencies".
    ("finance_cost", r"^(finance costs?|interest expenses?|finance charges|interest expended)", None),
    ("impairment", r"^(impairment (on|of) financial|impairment on loans|provisions and write|provisions \(other than tax\)|provisions and contingencies)", None),
    ("dna", r"depreciation", None),
    ("other_exp", r"^other expenses", None),
    ("total_exp", r"^total expenses", None),
    ("pbt_pre_exc", r"before exceptional", None),
    ("exceptional", r"^exceptional", None),
    ("pbt", r"before tax", r"exceptional"),
    ("tax", r"^(total tax expense|tax expense)", r"deferred|current tax"),
    ("pat", r"^(net )?profit(\s*/?\s*\(?loss\)?)?\s*(for the (period|quarter|year)|after tax)", r"attributable|comprehensive|owners|non-controlling|discontinued"),
]

BS_FIELDS: list[tuple[str, str, str | None, set[str] | None]] = [
    # key, pattern, exclude, allowed sections (None = any)
    ("total_assets", r"^total assets", None, None),
    ("total_eq_liab", r"^total (equity and liabilities|liabilities and equity)", None, None),
    ("total_equity", r"^total equity$|^total equity attributable|^equity attributable to (the )?owners", r"liabilities", None),
    ("borrowings", r"^(borrowings|debt securities|subordinated liabilities|deposits)\b", r"lease", {"nc_liab", "c_liab", "fin_liab", "liab", "bank_liab"}),
    ("cash", r"^cash and cash equivalents|^cash and balances? with (the )?reserve bank", None, None),
    ("bank_balances", r"^(other )?bank balances?|^balances? with banks", None, None),
    ("current_investments", r"^(current )?investments", None, {"c_assets"}),
    ("receivables", r"^trade receivables", None, None),
    ("inventories", r"^inventories", None, None),
    ("payables", r"^trade payables|^total outstanding dues", None, None),
    ("loans", r"^loans\b|^advances$|^advances \(net\)", None, {"fin_assets", "bank_assets"}),
    # Bank balance sheets end each side with a bare "Total".
    ("total_eq_liab", r"^total$", None, {"bank_liab"}),
    ("total_assets", r"^total$", None, {"bank_assets"}),
]

SECTIONS = [
    ("nc_assets", r"^non[- ]current assets"),
    ("c_assets", r"^current assets"),
    ("fin_assets", r"^financial assets"),
    ("nonfin_assets", r"^non[- ]financial assets"),
    ("nc_liab", r"^non[- ]current liabilities"),
    ("c_liab", r"^current liabilities"),
    ("fin_liab", r"^financial liabilities"),
    ("nonfin_liab", r"^non[- ]financial liabilities"),
    ("equity", r"^equity$"),
    ("liab", r"^liabilities$|^equity and liabilities|^liabilities and equity"),
    ("bank_liab", r"^capital and liabilities"),
    ("bank_assets", r"^assets$"),
]

CF_FIELDS: list[tuple[str, str, str | None]] = [
    ("cfo", r"^net cash.*operating activities", None),
    ("capex", r"^(purchase|acquisition|payment)s? (of|for) (property|fixed assets|tangible|intangible|capital work)|^capital expenditure", None),
    ("capex_proceeds", r"^proceeds from (sale|disposal) of (property|fixed assets)", None),
    ("cfi", r"^net cash.*investing activities", None),
    ("cff", r"^net cash.*financing activities", None),
]


def _basis(text: str) -> str:
    head = text[:1500].lower()
    return "consolidated" if "consolidated" in head else "standalone" if "standalone" in head else "unknown"


CONTINUATION = re.compile(r"^(and|or|of|for|from|to|in|on|at|with|by|the|before|after|attributable|\(|&)")


def _label_rows(rows: list[Row]) -> list[tuple[str, Row]]:
    """Joins a numberless line to the next line when the next line continues it.

    "Profit before exceptional items" / "and tax" wraps; "Expenses" / "Cost of
    materials consumed" is a heading followed by a new line item. A line is a
    continuation only if its original text starts in lower case or with a
    connecting word.
    """
    out: list[tuple[str, Row]] = []
    pending: str | None = None
    for r in rows:
        first = next((t for t in r.text.split() if re.search(r"[A-Za-z]{2,}", t) and not SERIAL.match(t)), "")
        cont = bool(first) and (first[:1].islower() or bool(CONTINUATION.match(first.lower())) and not first[:1].isupper())
        if not r.numbers:
            if pending and cont:
                pending = pending + " " + r.label
            else:
                pending = r.label
            out.append((r.label, r))
            continue
        out.append(((pending + " " + r.label) if pending and cont else r.label, r))
        pending = None
    return out


def _original_label(row: Row) -> str:
    """The row label as printed (case kept), without serial markers or numbers."""
    toks = row.text.split()
    while toks and (SERIAL.match(toks[0]) or not re.search(r"[A-Za-z]{2,}", toks[0])):
        toks.pop(0)
    out = []
    for t in toks:
        if re.match(r"^\(?-?[\d,]*\d(\.\d+)?\)?$", t) or t in ("-", "–"):
            break
        out.append(t)
    return " ".join(out).strip(" :")


def _pick(pages: list[tuple[int, pymupdf.Page, str]], test) -> tuple[int, pymupdf.Page, str, str] | None:
    cands = [(pno, pg, txt, _basis(txt)) for pno, pg, txt in pages if test(txt.lower())]
    if not cands:
        return None
    return sorted(cands, key=lambda c: {"consolidated": 0, "unknown": 1, "standalone": 2}[c[3]])[0]


def parse(pdf_bytes: bytes, is_financial: bool) -> Statements:
    st = Statements()
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        st.status, st.reason = "failed", f"PDF could not be opened: {e}"
        return st
    pages = [(i, p, p.get_text()) for i, p in enumerate(doc, start=1)]
    if all(len(t.strip()) < 200 for _, _, t in pages):
        st.status = "failed"
        st.reason = "no text layer: the PDF looks scanned (OCR is not enabled)" if any(p.get_images() for _, p, _ in pages) else "no text in the PDF"
        return st

    pnl = _pick(pages, lambda t: "before tax" in t and re.search(r"revenue from operations|income from operations|interest earned|net sales", t) and "cash flow" not in t[:600])
    if not pnl:
        st.status, st.reason = "failed", "no results statement found in the PDF"
        return st
    pno, page, text, basis = pnl
    st.basis["P&L"] = basis
    st.unit, factor = _unit(text)
    cols = _date_columns(page, 3)
    labels = pnl_labels(cols)
    if not labels:
        st.status, st.reason = "failed", "header dates don't match the SEBI column order (this quarter, previous quarter, same quarter last year)"
        return st
    st.current = labels[0]
    in_exp = False
    for lab, row in _label_rows(rows_from_page(page)):
        if re.match(r"^expenses\b", row.label) and not row.numbers:
            in_exp = True
            continue
        if not row.numbers:
            continue
        for key, pat, exc in PNL_FIELDS:
            if any(key in st.pnl.get(l, {}) for l in labels[:1] if l):
                continue
            if re.search(pat, lab) and not (exc and re.search(exc, lab)):
                for i, v in enumerate(_assign(row, cols)):
                    if v is None or not labels[i]:
                        continue
                    st.pnl.setdefault(labels[i], {}).setdefault(key, Cell(round(v * factor, 2), pno, row.text[:200], cols[i][2], "P&L", basis))
                break
        else:
            # Any other itemised expense line ("Power and fuel", "Freight"), so a margin change can be split by cost line.
            if in_exp:
                name = _original_label(row)
                key = "x:" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]
                st.labels[key] = name
                for i, v in enumerate(_assign(row, cols)):
                    if v is not None and labels[i]:
                        st.pnl.setdefault(labels[i], {}).setdefault(key, Cell(round(v * factor, 2), pno, row.text[:200], cols[i][2], "P&L", basis))
        if re.match(r"^total expenses", row.label):
            in_exp = False

    # Statement of assets and liabilities.
    bs = _pick(pages, lambda t: ("assets and liabilities" in t[:1500] or "balance sheet" in t[:1500]) and ("total assets" in t or "capital and liabilities" in t))
    if bs:
        bno, bpage, btext, bbasis = bs
        st.basis["Balance sheet"] = bbasis
        _, bfactor = _unit(btext)
        bfactor = bfactor if _unit(btext)[0] else factor
        bcols = _date_columns(bpage, 2)
        section: str | None = None
        for lab, row in _label_rows(rows_from_page(bpage)):
            for sk, sp in SECTIONS:
                # Corporates nest "Financial assets" inside current/non-current; lenders lead with it.
                if sk.startswith(("fin_", "nonfin_", "bank_")) != is_financial and sk not in ("equity", "liab"):
                    continue
                if re.search(sp, row.label):
                    section = sk
            if not row.numbers or not bcols:
                continue
            for key, pat, exc, allowed in BS_FIELDS:
                if key == "loans" and not is_financial:
                    continue
                if key == "current_investments" and is_financial:
                    continue
                if re.search(pat, row.label) and not (exc and re.search(exc, row.label)) and (allowed is None or section in allowed):
                    for i, v in enumerate(_assign(row, bcols)):
                        lab_i = _bs_label(bcols[i][1])
                        if v is None or not lab_i:
                            continue
                        cell = Cell(round(v * bfactor, 2), bno, row.text[:200], bcols[i][2], "Balance sheet", bbasis)
                        bucket = st.bs.setdefault(lab_i, {})
                        if key in ("borrowings", "payables") and key in bucket:
                            prev = bucket[key]
                            bucket[key] = Cell(round(prev.value + cell.value, 2), bno, prev.row_text + " | " + cell.row_text, cell.column, "Balance sheet", bbasis)
                        else:
                            bucket.setdefault(key, cell)
                    break
        for lab_i, b in st.bs.items():
            if "total_assets" in b and "total_eq_liab" in b:
                ok = abs(b["total_assets"].value - b["total_eq_liab"].value) <= max(0.5, 0.001 * b["total_assets"].value)
                st.checks.append({"check": f"Total assets = total equity and liabilities ({lab_i})", "ok": ok, "detail": f"{b['total_assets'].value} vs {b['total_eq_liab'].value}"})

    # Cash flow statement.
    cf = _pick(pages, lambda t: "cash flow" in t[:1500] and "operating activities" in t)
    if cf:
        cno, cpage, ctext, cbasis = cf
        st.basis["Cash flow"] = cbasis
        cfactor = _unit(ctext)[1] if _unit(ctext)[0] else factor
        ccols = _date_columns(cpage, 2)
        for lab, row in _label_rows(rows_from_page(cpage)):
            if not row.numbers or not ccols:
                continue
            for key, pat, exc in CF_FIELDS:
                if re.search(pat, lab) and not (exc and re.search(exc, lab)):
                    for i, v in enumerate(_assign(row, ccols)):
                        lab_i = P.label_for_end(ccols[i][1], "ytd")
                        if v is None or not lab_i:
                            continue
                        bucket = st.cf.setdefault(lab_i, {})
                        cell = Cell(round(v * cfactor, 2), cno, row.text[:200], ccols[i][2], "Cash flow", cbasis)
                        if key == "capex" and key in bucket:
                            prev = bucket[key]
                            bucket[key] = Cell(round(prev.value + cell.value, 2), cno, prev.row_text + " | " + cell.row_text, cell.column, "Cash flow", cbasis)
                        else:
                            bucket.setdefault(key, cell)
                    break

    # Segment note: rows between "Segment revenue" and the first total.
    seg = _pick(pages, lambda t: "segment" in t and re.search(r"segment revenue|segment-wise revenue", t))
    if seg:
        sno, spage, stext, sbasis = seg
        sfactor = _unit(stext)[1] if _unit(stext)[0] else factor
        scols = _date_columns(spage, 3)
        slabels = pnl_labels(scols)
        inside = False
        for row in rows_from_page(spage):
            if re.search(r"segment revenue|segment-wise revenue", row.label):
                inside = True
                continue
            if not inside:
                continue
            if re.match(r"^(total|less|net|segment result|revenue from operations)", row.label) or not row.numbers:
                if row.numbers or re.match(r"^segment result", row.label):
                    break
                continue
            name = _original_label(row)
            for i, v in enumerate(_assign(row, scols)):
                if v is None or not slabels or i > 2 or not slabels[i]:
                    continue
                st.segments.setdefault(slabels[i], {})[name] = Cell(round(v * sfactor, 2), sno, row.text[:200], scols[i][2], "Segment note", sbasis)

    # Identity checks on the P&L.
    for lab in labels[:3]:
        if not lab:
            continue
        f = st.pnl.get(lab, {})
        if all(k in f for k in ("pbt", "tax", "pat")):
            diff = abs(f["pbt"].value - f["tax"].value - f["pat"].value)
            st.checks.append({"check": f"PBT - tax = PAT ({lab})", "ok": diff <= max(0.5, 0.015 * abs(f["pat"].value)), "detail": f"{f['pbt'].value} - {f['tax'].value} vs {f['pat'].value}"})
    cur = st.pnl.get(st.current or "", {})
    missing = [k for k in ("revenue", "pbt", "pat") if k not in cur]
    if missing:
        st.status, st.reason = "needs_review", f"missing rows in the current quarter: {', '.join(missing)}"
    elif not all(c["ok"] for c in st.checks):
        st.status, st.reason = "needs_review", "; ".join(c["check"] for c in st.checks if not c["ok"]) + " failed"
    return st
