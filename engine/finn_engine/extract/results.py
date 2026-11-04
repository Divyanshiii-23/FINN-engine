"""Quarterly results extraction from the SEBI-format results PDF.

No model is involved. Rows are rebuilt from word positions, numbers are
assigned to columns by the x-position of the header dates, units are read
from the statement header, and every metric, delta and margin is computed in
code with the formula and source row recorded.

SEBI's format prints three quarterly columns side by side: this quarter, the
preceding quarter, and the same quarter last year. That is why QoQ and YoY
can come from a single filing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pymupdf

from .. import EXTRACTOR_VERSION
from ..models import Evidence, Figure, ResultsExtraction, ResultsRow

NUM = re.compile(r"^\(?-?[\d,]*\d(\.\d+)?\)?$")
DASH = {"-", "–", "—", "nil", "Nil", "NIL"}
SERIAL = re.compile(r"^(\(?[ivxlc]+\)?\.?|\(?[a-z]\)\.?|\d{1,2}\.?|\(\d{1,2}\))$", re.I)
DATE = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
UNIT = re.compile(r"(?:₹|rs\.?|inr|rupees)\s*(?:in\s*)?(lakhs?|lacs?|crores?|crs?\.?|millions?|mn)\b|\(in\s*(lakhs?|lacs?|crores?|millions?)\)", re.I)
UNIT_FACTOR = {"lakh": 0.01, "lac": 0.01, "crore": 1.0, "cr": 1.0, "million": 0.1, "mn": 0.1}

FIELDS: list[tuple[str, re.Pattern[str], re.Pattern[str] | None]] = [
    ("revenue", re.compile(r"^(revenue from operations|income from operations|total revenue from operations|net sales|interest earned)"), None),
    ("other_income", re.compile(r"^other income"), None),
    ("finance_cost", re.compile(r"^(finance costs?|interest expenses?|finance charges)"), None),
    ("dna", re.compile(r"depreciation"), None),
    ("pbt_pre_exc", re.compile(r"before exceptional"), None),
    ("exceptional", re.compile(r"^exceptional"), None),
    ("pbt", re.compile(r"before tax"), re.compile(r"exceptional")),
    ("tax", re.compile(r"^(total tax expense|tax expense)"), re.compile(r"deferred|current tax")),
    ("pat", re.compile(r"^(net )?profit(\s*/?\s*\(?loss\)?)?\s*(for the (period|quarter|year)|after tax)"), re.compile(r"attributable|comprehensive|owners|non-controlling|discontinued")),
]


@dataclass
class Row:
    y: float
    label: str
    numbers: list[tuple[float, float | None]]  # (x-centre, value) ; value None for a dash
    text: str


def rows_from_page(page: pymupdf.Page, tol: float = 3.0) -> list[Row]:
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list[tuple]] = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if lines and abs(((lines[-1][0][1] + lines[-1][0][3]) / 2) - yc) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    out: list[Row] = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        toks = [w[4] for w in ln]
        # Drop leading serial markers ("1", "I.", "(a)", "IV", "(ii)") before the label.
        first_alpha = next((i for i, t in enumerate(toks) if not SERIAL.match(t) and re.search(r"[A-Za-z]{2,}", t)), None)
        if first_alpha is None:
            continue
        label_parts: list[str] = []
        nums: list[tuple[float, float | None]] = []
        for w in ln[first_alpha:]:
            t = w[4]
            xc = (w[0] + w[2]) / 2
            if NUM.match(t) and label_parts:
                neg = t.startswith("(") and t.endswith(")")
                v = float(t.strip("()").replace(",", ""))
                nums.append((xc, -v if neg else v))
            elif t in DASH and label_parts:
                # In Indian results formats a dash or "nil" in a figure column means zero, not
                # "not reported"; keeping it as zero lets EBITDA and similar sums be computed.
                nums.append((xc, 0.0))
            elif not nums:
                label_parts.append(t)
        out.append(Row(y=(ln[0][1] + ln[0][3]) / 2, label=" ".join(label_parts).lower(), numbers=nums, text=" ".join(toks)))
    return out


def header_columns(page: pymupdf.Page) -> list[tuple[float, date]]:
    """x-centres and dates of the date tokens in the column header row."""
    words = page.get_text("words")
    by_line: dict[int, list[tuple[float, date]]] = {}
    for w in words:
        m = DATE.search(w[4])
        if not m:
            continue
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = date(y, mth, d)
        except ValueError:
            continue
        key = int(round(((w[1] + w[3]) / 2) / 4))
        by_line.setdefault(key, []).append(((w[0] + w[2]) / 2, dt))
    best = max(by_line.values(), key=len, default=[])
    return sorted(best, key=lambda t: t[0]) if len(best) >= 3 else []


def quarter_label(d: date) -> str | None:
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    if not q:
        return None
    fy = d.year + 1 if d.month >= 4 else d.year
    return f"Q{q} FY{fy % 100:02d}"


def _months_between(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def _assign(row: Row, cols: list[tuple[float, date]] | None) -> list[float | None]:
    """Values for the first three columns (current, previous quarter, same quarter last year)."""
    if cols:
        out: list[float | None] = [None, None, None]
        for xc, v in row.numbers:
            idx = min(range(len(cols)), key=lambda i: abs(cols[i][0] - xc))
            if idx < 3 and abs(cols[idx][0] - xc) < 60:
                out[idx] = v
        return out
    vals = [v for _, v in row.numbers[:3]]
    return vals + [None] * (3 - len(vals))


def _unit(text: str) -> tuple[str | None, float]:
    m = UNIT.search(text)
    if not m:
        return None, 1.0
    u = (m.group(1) or m.group(2)).lower().rstrip("s.")
    for k, f in UNIT_FACTOR.items():
        if u.startswith(k):
            return k, f
    return None, 1.0


def _growth(cur: float | None, base: float | None) -> float | None:
    if cur is None or base is None or base <= 0:
        return None
    return cur / base - 1


def extract_pdf(pdf_bytes: bytes, is_financial: bool = False) -> ResultsExtraction:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        return ResultsExtraction(status="failed", reason=f"PDF could not be opened: {e}", extractor_version=EXTRACTOR_VERSION)

    candidates = []
    for pno, page in enumerate(doc, start=1):
        text = page.get_text()
        low = text.lower()
        if "before tax" not in low or not re.search(r"revenue from operations|income from operations|interest earned|net sales", low):
            continue
        head = low[:1200]
        basis = "consolidated" if "consolidated" in head else "standalone" if "standalone" in head else "unknown"
        candidates.append((pno, page, basis, text))
    if not candidates:
        scanned = all(len(p.get_text().strip()) < 200 for p in doc) and any(p.get_images() for p in doc)
        reason = "no text layer: the PDF looks scanned (OCR not enabled)" if scanned else "no results statement found in the PDF"
        return ResultsExtraction(status="failed", reason=reason, extractor_version=EXTRACTOR_VERSION)

    pno, page, basis, text = sorted(candidates, key=lambda c: {"consolidated": 0, "unknown": 1, "standalone": 2}[c[2]])[0]
    unit_name, factor = _unit(text)
    cols = header_columns(page)
    column_order = None
    period = None
    if len(cols) >= 3:
        d0, d1, d2 = cols[0][1], cols[1][1], cols[2][1]
        if 2 <= _months_between(d0, d1) <= 4 and 11 <= _months_between(d0, d2) <= 13:
            column_order = "header_dates"
            period = quarter_label(d0)
        else:
            cols = []
    if not cols:
        column_order = "assumed_sebi_standard"

    found: dict[str, tuple[list[float | None], str]] = {}
    for row in rows_from_page(page):
        if not row.numbers:
            continue
        for key, pat, exc in FIELDS:
            if key in found:
                continue
            if pat.search(row.label) and not (exc and exc.search(row.label)):
                vals = [None if v is None else round(v * factor, 2) for v in _assign(row, cols or None)]
                found[key] = (vals, row.text)
                break

    def fig(key: str, i: int) -> Figure:
        if key not in found:
            return Figure(value=None)
        vals, txt = found[key]
        return Figure(value=vals[i], evidence=Evidence(kind="pdf_row", page=pno, text=txt[:200]))

    checks: list[dict] = []
    rows: list[ResultsRow] = []
    ebitda_formula = "PBT before exceptional items + finance costs + depreciation and amortisation - other income"

    def ebitda(i: int) -> Figure:
        base_key = "pbt_pre_exc" if "pbt_pre_exc" in found else "pbt"
        parts = [found.get(k, (None,))[0] for k in (base_key, "finance_cost", "dna", "other_income")]
        if any(p is None or p[i] is None for p in parts):
            return Figure(value=None)
        p, f, d, o = (x[i] for x in parts)  # type: ignore[index]
        v = round(p + f + d - o, 2)
        label = "PBT before exceptional" if base_key == "pbt_pre_exc" else "PBT"
        return Figure(value=v, evidence=Evidence(kind="computed", page=pno, formula=f"{label} {p} + finance costs {f} + D&A {d} - other income {o} = {v}"))

    def mk(key: str, label: str, getter) -> ResultsRow:
        cur, pq, py = getter(0), getter(1), getter(2)
        return ResultsRow(key=key, label=label, current=cur, prev_q=pq, prev_y=py, qoq=_growth(cur.value, pq.value), yoy=_growth(cur.value, py.value))

    rows.append(mk("revenue", "Revenue from operations" if not is_financial else "Revenue (interest earned)", lambda i: fig("revenue", i)))
    if is_financial:
        rows.append(ResultsRow(key="ebitda", label="EBITDA (not meaningful for lenders)", current=Figure(value=None), prev_q=Figure(value=None), prev_y=Figure(value=None)))
    else:
        rows.append(mk("ebitda", "EBITDA", ebitda))
    rows.append(mk("pbt", "Profit before tax", lambda i: fig("pbt", i)))
    rows.append(mk("pat", "Profit after tax", lambda i: fig("pat", i)))

    required = ["revenue", "pbt", "pat"]
    missing = [k for k in required if k not in found or any(v is None for v in found[k][0])]
    if missing:
        checks.append({"check": "required rows present", "ok": False, "detail": f"missing or incomplete: {', '.join(missing)}"})
    else:
        checks.append({"check": "required rows present", "ok": True, "detail": "revenue, PBT and PAT found in all three columns"})
    if "tax" in found and not missing:
        for i, col in enumerate(("current", "previous quarter", "same quarter last year")):
            pbt, tax, pat = found["pbt"][0][i], found["tax"][0][i], found["pat"][0][i]
            if None in (pbt, tax, pat):
                continue
            diff = abs(pbt - tax - pat)
            tol = max(0.5, 0.015 * abs(pat))
            checks.append({"check": f"PBT - tax = PAT ({col})", "ok": diff <= tol, "detail": f"{pbt} - {tax} = {round(pbt - tax, 2)} vs PAT {pat}"})
    if column_order == "assumed_sebi_standard":
        checks.append({"check": "column order", "ok": False, "detail": "header dates not found; assumed SEBI order (current, previous quarter, same quarter last year)"})

    margin = None
    rev = rows[0]
    eb = rows[1]
    if not is_financial and eb.current.value is not None and rev.current.value:
        def m(f: Figure, r: Figure) -> float | None:
            return f.value / r.value if f.value is not None and r.value else None
        margin = {"current": m(eb.current, rev.current), "prev_q": m(eb.prev_q, rev.prev_q), "prev_y": m(eb.prev_y, rev.prev_y)}

    status = "ok" if not missing and all(c["ok"] for c in checks if c["check"] != "column order") else "needs_review"
    if column_order == "assumed_sebi_standard" and status == "ok":
        status = "needs_review"
    return ResultsExtraction(
        status=status,
        reason=None if status == "ok" else "; ".join(c["detail"] for c in checks if not c["ok"]),
        basis=basis,  # type: ignore[arg-type]
        unit_detected=unit_name,
        period_label=period,
        column_order=column_order,
        page=pno,
        rows=rows,
        ebitda_formula=None if is_financial else ebitda_formula,
        margin=margin,
        checks=checks,
        extractor_version=EXTRACTOR_VERSION,
    )
