"""A. Data integrity.

A1  every reported figure re-read from the PDF page it cites, with an extractor written
    for this evaluation (word coordinates; not FINN's parser), and compared with the report
A2  every reported P&L figure compared with the values the fixture generator planted
A3  QoQ / YoY / margin / margin-change facts recomputed from the planted values
A4  every computed fact recomputed from its own inputs by formula family
A5  displayed text agrees with the stored value
A6  negative, zero and bracketed values through FINN's own parsers (constructed PDFs)
A7  missing data: gaps stated, nothing filled in
A8  reporting-period mismatches
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from finn_engine.research import fixtures as RF  # noqa: E402
from finn_engine.research import periods as P  # noqa: E402
from finn_engine.research import statements as S  # noqa: E402
from finn_engine.research.financials import Facts, Numbers  # noqa: E402
from finn_engine.research.models import Doc  # noqa: E402

NUMW = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?$")


def _num(t: str) -> float | None:
    t = t.strip()
    if t in ("-", "–", "—", "Nil", "nil", "NIL"):
        return 0.0
    if not NUMW.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def _factor(text: str) -> float:
    m = re.search(r"in\s+(lakhs?|lacs?|crores?|millions?)", text, re.I)
    u = (m.group(1).lower() if m else "crore")
    return 0.01 if u.startswith(("lakh", "lac")) else 0.1 if u.startswith("million") else 1.0


class PdfReader:
    """Independent figure lookup: header date x-position x row label y-position."""

    def __init__(self):
        self.cache: dict[str, pymupdf.Document] = {}

    def page(self, path: str, n: int):
        if path not in self.cache:
            self.cache[path] = pymupdf.open(path)
        return self.cache[path][n - 1]

    def value(self, path: str, pno: int, row_text: str, column: str, period: str) -> tuple[list[float], str]:
        pg = self.page(path, pno)
        words = pg.get_text("words")
        fac = _factor(pg.get_text())
        heads = sorted([((w[0] + w[2]) / 2, w[1]) for w in words if w[4] == column], key=lambda h: h[0])
        if not heads:
            return [], f"column {column} not on page {pno}"
        # Quarter figures sit in the first column with that date; year/half-year/YTD in the last.
        hx = heads[0][0] if period.startswith("Q") else heads[-1][0]
        hy = max(h[1] for h in heads)
        label = [t for t in row_text.split() if _num(t) is None and re.search(r"[A-Za-z]", t)]
        # Group words into visual rows by vertical position (labels and figures are separate text blocks).
        rows: list[list] = []
        for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
            yc = (w[1] + w[3]) / 2
            if rows and abs(rows[-1][0] - yc) <= 2.5:
                rows[-1][1].append(w)
            else:
                rows.append([yc, [w]])
        found = []
        for _, ws in rows:
            ws = sorted(ws, key=lambda w: w[0])
            if ws[0][1] <= hy:
                continue
            text_words = [w[4] for w in ws]
            if label and not all(lt in text_words for lt in label[:4]):
                continue
            # Same label twice on a page (non-current and current borrowings): the figures in the cited row decide.
            row_nums = [t for t in row_text.split() if _num(t) is not None and re.search(r"\d", t)]
            if row_nums and not all(t in text_words for t in row_nums[:2]):
                continue
            nums = [((w[0] + w[2]) / 2, _num(w[4])) for w in ws if _num(w[4]) is not None and not re.fullmatch(r"\(?[ivxIVX]+\)?|\(?[a-z]\)", w[4])]
            near = [v for x, v in nums if abs(x - hx) < 45]
            if near:
                found.append(round(near[0] * fac, 2))
        return found, f"{len(found)} matching row(s); unit factor {fac}"


def run(rec, reps: dict, inputs_dir: Path) -> None:
    truth = RF.truth()
    rd = PdfReader()

    # ---------------------------------------------------------------- A1, A2
    n_pdf = n_pdf_ok = 0
    for sym, r in reps.items():
        docs = {d["id"]: d for d in r["documents"]}
        for f in r["facts"].values():
            if f["info_class"] != "reported" or not f.get("row_text") or not f.get("column"):
                continue
            d = docs.get(f["doc_id"])
            if not d or not d.get("raw_path"):
                rec.check("A", "A1 values vs PDF", f"{sym} {f['id']}", False, "no document path to verify against", severity="critical")
                continue
            parts = f["row_text"].split(" | ")
            if len(parts) > 1:  # a figure FINN sums across rows (current + non-current borrowings): re-read each row and add
                got = [rd.value(d["raw_path"], f["page"], pt, f["column"], f.get("period") or "Q") for pt in parts]
                vals = [round(sum(g[0][0] for g in got if g[0]), 2)] if all(g[0] for g in got) else []
                how = f"sum of {len(parts)} rows"
            else:
                vals, how = rd.value(d["raw_path"], f["page"], f["row_text"], f["column"], f.get("period") or "Q")
            ok = any(abs(v - f["value"]) <= 0.011 + 1e-6 * abs(f["value"]) for v in vals)
            n_pdf += 1
            n_pdf_ok += ok
            if not ok:
                rec.check("A", "A1 values vs PDF", f"{sym} {f['id']}", False, f"report {f['value']} vs PDF {vals[:3]} ({how}) page {f['page']}", severity="critical")
        rec.check("A", "A1 values vs PDF", f"{sym}: reported figures re-read from the PDF", True, "summary row")
        # A2: planted P&L values
        if sym not in truth:
            continue
        pl = truth[sym]["pl"]
        miss = []
        cnt = 0
        for f in r["facts"].values():
            m = re.match(r"r:pl:(Q[1-4]FY\d\d):(\w+)$", f["id"])
            if not m or f.get("basis") not in (None, "consolidated"):
                continue
            q = m.group(1)[:2] + " " + m.group(1)[2:]
            k = m.group(2)
            if q in pl and k in pl[q]:
                cnt += 1
                if abs(pl[q][k] - f["value"]) > 0.011 + 1e-6 * abs(pl[q][k]):
                    miss.append(f"{f['id']}: {f['value']} vs planted {pl[q][k]}")
        rec.check("A", "A2 values vs planted truth", f"{sym} P&L ({cnt} figures)", not miss and cnt > 0, "; ".join(miss[:4]) or f"{cnt} matched", severity="critical")
    rec.metric("A1_figures_checked_against_pdf", n_pdf)
    rec.metric("A1_figures_matching_pdf", n_pdf_ok)

    # ---------------------------------------------------------------- A3: QoQ / YoY / margins from planted values
    for sym, r in reps.items():
        if sym not in truth:
            continue
        pl, fac = truth[sym]["pl"], r["facts"]
        bad, n = [], 0
        for q in pl:
            for base in (P.shift_year(q), P.prev_q(q)):
                for k in ("revenue", "pat"):
                    fid = f"c:{q.replace(' ', '')}:{k}_growth_{base.replace(' ', '')}"
                    if fid in fac and base in pl and pl[base].get(k):
                        n += 1
                        want = pl[q][k] / pl[base][k] - 1
                        if abs(fac[fid]["value"] - want) > 5e-4:
                            bad.append(f"{fid} {fac[fid]['value']:.4f} vs {want:.4f}")
            if not r["identity"]["is_financial"]:
                fid = f"c:{q.replace(' ', '')}:ebitda_margin"
                if fid in fac and "ebitda" in pl[q] and pl[q].get("revenue"):
                    n += 1
                    want = pl[q]["ebitda"] / pl[q]["revenue"]
                    if abs(fac[fid]["value"] - want) > 5e-4:
                        bad.append(f"{fid} {fac[fid]['value']:.4f} vs {want:.4f}")
                yo = P.shift_year(q)
                fid = f"c:{q.replace(' ', '')}:ebitda_margin_chg_{yo.replace(' ', '')}"
                if fid in fac and yo in pl and "ebitda" in pl[q] and "ebitda" in pl[yo]:
                    n += 1
                    want = (pl[q]["ebitda"] / pl[q]["revenue"] - pl[yo]["ebitda"] / pl[yo]["revenue"]) * 100
                    if abs(fac[fid]["value"] - want) > 0.02:
                        bad.append(f"{fid} {fac[fid]['value']:.3f} vs {want:.3f} pp")
        rec.check("A", "A3 QoQ/YoY/margins vs truth", f"{sym} ({n} computed)", n > 0 and not bad, "; ".join(bad[:4]) or f"{n} within tolerance", severity="critical")

    # ---------------------------------------------------------------- A4: computed facts from their inputs
    for sym, r in reps.items():
        fac = r["facts"]
        n = skipped = 0
        bad = []
        for f in fac.values():
            if f["info_class"] != "computed" or f.get("value") is None:
                continue
            ins = [fac[i].get("value") if i in fac else None for i in f.get("inputs", [])]
            if any(v is None for v in ins) or not ins:
                skipped += 1
                continue
            want = _recompute(f, ins)
            if want is None:
                skipped += 1
                continue
            n += 1
            tol = max(0.011, 2e-3 * abs(want)) if f["unit"] in ("cr", "days") else max(6e-4, 2e-3 * abs(want))
            if f["unit"] == "pp":
                tol = 0.011
            if abs(f["value"] - want) > tol:
                bad.append(f"{f['id']} {f['value']} vs {round(want, 4)}")
        rec.check("A", "A4 computed facts vs their inputs", f"{sym} ({n} recomputed, {skipped} not covered)", not bad, "; ".join(bad[:4]), severity="critical")
        rec.metric(f"A4_{sym}_recomputed", n)

    # ---------------------------------------------------------------- A5: display text agrees with value
    for sym, r in reps.items():
        bad = []
        for f in r["facts"].values():
            if f.get("value") is None or not f.get("display") or f["unit"] not in ("cr", "pct", "pp", "growth"):
                continue
            m = re.search(r"[-−+]?[\d,]+(\.\d+)?", f["display"])
            if not m:
                continue
            shown = float(m.group(0).replace(",", "").replace("−", "-"))
            if f["display"].lstrip().startswith(("-", "−")) and shown > 0:
                shown = -shown
            v = f["value"] * (100 if f["unit"] in ("pct", "growth") else 1)
            dec = len(m.group(1)) - 1 if m.group(1) else 0
            if abs(shown - v) > 0.5 * 10 ** -dec + 1e-9 or (v < -0.05 and shown > 0):
                bad.append(f"{f['id']} value {f['value']} shown '{f['display']}'")
        rec.check("A", "A5 display matches value", sym, not bad, "; ".join(bad[:4]))

    edge_cases(rec)
    missing_and_periods(rec, reps, inputs_dir)


def _recompute(f: dict, x: list[float]) -> float | None:
    fm, fid = f.get("formula") or "", f["id"]
    if ("_chg" in fid or "share_chg" in fid) and f["unit"] == "pp":
        return (x[0] - x[1]) * 100 if len(x) == 2 else None
    if fid.endswith("net_debt_chg") and len(x) == 2:
        return x[1] - x[0] if abs((x[1] - x[0]) - f["value"]) < abs((x[0] - x[1]) - f["value"]) else x[0] - x[1]
    if fid.endswith(":de") and len(x) == 2:
        return round(x[0] / x[1], 2)  # FINN stores debt/equity to two decimals
    if re.search(r"÷ .*- 1$|÷ same period last year - 1", fm) and "growth" in fid:
        if len(x) == 2:
            return x[0] / x[1] - 1
        return None
    if fid.endswith(":ebitda") and len(x) == 4:
        return x[0] + x[1] + x[2] - x[3]
    if fid.endswith(":ebit") and len(x) == 2:
        return x[0] - x[1]
    if fm.startswith("Purchase of property"):
        return abs(x[0])
    if fid.endswith((":fcf", ":nii")) and len(x) == 2:
        return x[0] - x[1]
    if fid.endswith(":net_debt") and len(x) >= 2:
        return x[0] - sum(x[1:])
    if fid.startswith("c:ttm:"):
        return sum(x)
    if fid.endswith(":wc_days") and len(x) == 4:
        return (x[0] + x[1] - x[2]) / x[3] * 365
    if fid.endswith(":rec_days") and len(x) == 2:
        return x[0] / x[1] * 365
    if "loan_growth_ytd" in fid and len(x) == 2:
        return x[0] / x[1] - 1
    if fid.endswith(":credit_cost") and len(x) == 3:
        m = re.search(r"× 4/(\d)", fm)
        return x[0] * 4 / int(m.group(1)) / ((x[1] + x[2]) / 2) if m else None
    if " ÷ " in fm and len(x) == 2 and "×" not in fm and " - " not in fm:
        return x[0] / x[1]
    return None


# ---------------------------------------------------------------- A6 edge cases through FINN's parsers

def _pdf(rows, cols_q="Q2 FY27", unit="(Rs. in crore)") -> bytes:
    pdf = RF.Pdf(rupee=False)
    cols = RF._columns(cols_q)
    p = pdf.page(landscape=True)
    pdf.text(p, (36, 44), "Edgecase Industries Limited", 11)
    pdf.text(p, (36, 60), "Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026", 9)
    pdf.text(p, (36, 74), unit, 7.5)
    RF._table(pdf, p, 100, [c for _, _, c in cols], [d for _, d, _ in cols], rows)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.pdf"
        pdf.save(f)
        return f.read_bytes()


def _numbers(rows, q="Q2 FY27"):
    st = S.parse(_pdf(rows, q), is_financial=False)
    n = Numbers.build(Facts(), [(Doc(id="d:x", kind="results", title="x", period=q, source="bse", status="parsed"), st)], is_financial=False)
    return st, n


def edge_cases(rec) -> None:
    # Columns: Q2 FY27, Q1 FY27, Q2 FY26, H1 FY27, H1 FY26, FY26
    def row(serial, label, vals):
        return (serial, label, vals)
    loss = [row("1", "Revenue from operations", ["500.00", "480.00", "520.00", "980.00", "1,010.00", "2,050.00"]),
            row("2", "Other income", ["5.00", "4.00", "6.00", "9.00", "11.00", "22.00"]),
            row("3", "Total income (1+2)", ["505.00", "484.00", "526.00", "989.00", "1,021.00", "2,072.00"]),
            row("4", "Expenses", []),
            row("(a)", "  Cost of materials consumed", ["420.00", "400.00", "380.00", "820.00", "760.00", "1,560.00"]),
            row("(b)", "  Finance costs", ["30.00", "28.00", "20.00", "58.00", "40.00", "90.00"]),
            row("(c)", "  Depreciation and amortisation expense", ["40.00", "40.00", "38.00", "80.00", "76.00", "156.00"]),
            row("(d)", "  Other expenses", ["75.00", "70.00", "60.00", "145.00", "120.00", "250.00"]),
            row("", "Total expenses", ["565.00", "538.00", "498.00", "1,103.00", "996.00", "2,056.00"]),
            row("5", "Profit/(loss) before exceptional items and tax", ["(60.00)", "(54.00)", "28.00", "(114.00)", "25.00", "16.00"]),
            row("6", "Exceptional items", ["-", "-", "-", "-", "-", "-"]),
            row("7", "Profit/(loss) before tax", ["(60.00)", "(54.00)", "28.00", "(114.00)", "25.00", "16.00"]),
            row("8", "Total tax expense", ["(15.00)", "(13.50)", "7.00", "(28.50)", "6.25", "4.00"]),
            row("9", "Net profit/(loss) for the period", ["(45.00)", "(40.50)", "21.00", "(85.50)", "18.75", "12.00"])]
    st, n = _numbers(loss)
    q = st.pnl.get("Q2 FY27", {})
    rec.check("A", "A6 negative/zero edge cases", "bracketed loss parsed as negative", q.get("pat") and q["pat"].value == -45.0, f"pat={q.get('pat') and q['pat'].value}", severity="critical")
    g = n.growth("Q2 FY27", "pat")
    rec.check("A", "A6 negative/zero edge cases", "PAT growth on a profit-to-loss swing is not reported as a %", g is None or g.value < 0,
              f"growth={g and g.value}", severity="critical")
    gq = n.growth("Q2 FY27", "pat", "Q1 FY27")
    rec.check("A", "A6 negative/zero edge cases", "PAT growth against a loss base is suppressed", gq is None, f"growth vs a -40.5 base = {gq and gq.value}", severity="critical")
    e = n.ebitda("Q2 FY27")
    rec.check("A", "A6 negative/zero edge cases", "EBITDA with a loss: PBT -60 + 30 + 40 - 5 = 5", e is not None and abs(e.value - 5.0) < 0.01, f"ebitda={e and e.value}")
    nm = n.margin("Q2 FY27", "ebit") if hasattr(n, "margin") else None
    eb = n.ebit("Q2 FY27") if hasattr(n, "ebit") else None
    rec.check("A", "A6 negative/zero edge cases", "negative EBIT kept negative (5 - 40 = -35)", eb is not None and abs(eb.value + 35) < 0.01, f"ebit={eb and eb.value}")
    # Zero revenue (pre-revenue company)
    zero = [row("1", "Revenue from operations", ["-", "-", "-", "-", "-", "-"]), row("2", "Other income", ["2.00", "2.00", "1.00", "4.00", "2.00", "5.00"]),
            row("3", "Total income (1+2)", ["2.00", "2.00", "1.00", "4.00", "2.00", "5.00"]), row("4", "Expenses", []),
            row("(a)", "  Employee benefits expense", ["3.00", "3.00", "2.00", "6.00", "4.00", "9.00"]),
            row("(b)", "  Finance costs", ["-", "-", "-", "-", "-", "-"]),
            row("(c)", "  Depreciation and amortisation expense", ["0.50", "0.50", "0.40", "1.00", "0.80", "1.70"]),
            row("(d)", "  Other expenses", ["1.00", "1.00", "1.00", "2.00", "2.00", "4.00"]),
            row("", "Total expenses", ["4.50", "4.50", "3.40", "9.00", "6.80", "14.70"]),
            row("5", "Profit/(loss) before exceptional items and tax", ["(2.50)", "(2.50)", "(2.40)", "(5.00)", "(4.80)", "(9.70)"]),
            row("6", "Profit/(loss) before tax", ["(2.50)", "(2.50)", "(2.40)", "(5.00)", "(4.80)", "(9.70)"]),
            row("7", "Total tax expense", ["-", "-", "-", "-", "-", "-"]),
            row("8", "Net profit/(loss) for the period", ["(2.50)", "(2.50)", "(2.40)", "(5.00)", "(4.80)", "(9.70)"])]
    try:
        st, n = _numbers(zero)
        m = n.margin("Q2 FY27", "ebitda") if hasattr(n, "margin") else None
        gr = n.growth("Q2 FY27", "revenue")
        rec.check("A", "A6 negative/zero edge cases", "zero revenue: no margin, no growth, no crash", (m is None) and (gr is None), f"margin={m and m.value} growth={gr and gr.value}", severity="critical")
    except ZeroDivisionError as ex:
        rec.check("A", "A6 negative/zero edge cases", "zero revenue: no margin, no growth, no crash", False, f"ZeroDivisionError: {ex}", severity="critical")
    # Push extractor on the same loss statement
    from finn_engine.extract.results import extract_pdf
    ex = extract_pdf(_pdf(loss))
    pat = next((r for r in ex.rows if r.key == "pat"), None)
    rec.check("A", "A6 negative/zero edge cases", "push extractor: loss PAT negative, YoY growth suppressed (base positive, current negative is shown as a fall)",
              pat is not None and pat.current.value == -45.0 and (pat.yoy is None or pat.yoy < 0), f"pat={pat and pat.current.value} yoy={pat and pat.yoy}", severity="critical")
    rec.check("A", "A6 negative/zero edge cases", "push extractor: QoQ growth against a loss base suppressed", pat is not None and pat.qoq is None, f"qoq={pat and pat.qoq}", severity="critical")


# ---------------------------------------------------------------- A7, A8

def missing_and_periods(rec, reps: dict, inputs_dir: Path) -> None:
    coral = reps["CORAL"]
    rec.check("A", "A7 missing data", "CORAL (no documents): no reported or computed figures", not [f for f in coral["facts"].values() if f["info_class"] in ("reported", "computed") and f["id"] != "c:pe"],
              f"{len(coral['facts'])} facts", severity="critical")
    rec.check("A", "A7 missing data", "CORAL: gaps stated", len(coral["gaps"]) > 0, f"{len(coral['gaps'])} gaps")
    v = reps["VEDIKA"]
    calls = {d["period"] for d in v["documents"] if d["kind"] == "transcript" and d["status"] == "parsed"}
    rec.check("A", "A7 missing data", "VEDIKA: no Q1 FY27 transcript is invented", "Q1 FY27" not in calls, f"parsed calls {sorted(calls)}", severity="critical")
    rec.check("A", "A7 missing data", "VEDIKA: missing Q1 FY27 call stated as a gap", any("Q1 FY27" in (g.get("text") or g.get("message") or str(g)) for g in v["gaps"]), str([g for g in v["gaps"]][:3])[:300])
    no_claims = [c for c in v["claims"] if c.get("call_period") == "Q1 FY27" and c.get("doc_kind") == "transcript"]
    rec.check("A", "A7 missing data", "VEDIKA: no claims attributed to the missing Q1 FY27 call", not no_claims, str(len(no_claims)), severity="critical")
    k = reps["KAVERI"]
    scanned = [d for d in k["documents"] if d["kind"] == "presentation" and d["status"] != "parsed"]
    rec.check("A", "A7 missing data", "KAVERI: scanned presentation reported unreadable, not parsed", bool(scanned) and all("scan" in (d.get("status_reason") or "").lower() or "text" in (d.get("status_reason") or "").lower() for d in scanned),
              str([(d["title"], d["status"], d.get("status_reason")) for d in scanned])[:300])
    h = reps["HALCYON"]
    q1 = [d for d in h["documents"] if d["kind"] == "transcript" and d["period"] == "Q1 FY27"]
    rec.check("A", "A7 missing data", "HALCYON: Q1 FY27 transcript read from the NSE copy when the BSE copy is missing", any(d["status"] == "parsed" for d in q1),
              str([(d["source"], d["status"], d["parse"].get("downloaded_from")) for d in q1])[:300])
    # Trajectory: a missing value must be None, never 0
    for sym, r in reps.items():
        tr = r["sections"]["trajectory"]
        bad = []
        for key, ids in tr.get("series", {}).items():
            for q, fid in zip(tr["quarters"], ids):
                if fid is not None and fid not in r["facts"]:
                    bad.append(f"{key} {q}: dangling {fid}")
                elif fid is not None and r["facts"][fid].get("value") is None:
                    bad.append(f"{key} {q}: fact without a value")
        rec.check("A", "A7 missing data", f"{sym}: trajectory gaps are empty, never placeholders or dangling ids", not bad, "; ".join(bad[:4]))

    # A8 period mismatches
    for sym, r in reps.items():
        res = [d for d in r["documents"] if d["kind"] == "results" and d["status"] == "parsed"]
        old = [d for d in r["documents"] if d.get("period") == RF.OLD_RESULTS and d["kind"] == "results"]
        rec.check("A", "A8 period mismatches", f"{sym}: Q4 FY24 filing outside the window is not used", not any(d["status"] == "parsed" for d in old), str([(d["period"], d["status"]) for d in old]))
        bad = []
        for d in res:
            # Every reported P&L fact from this document for its own quarter must carry the document's period column date.
            end = P.end_of(d["period"]) if d.get("period") else None
            for f in r["facts"].values():
                if f.get("doc_id") == d["id"] and f["id"].startswith(f"r:pl:{(d['period'] or '').replace(' ', '')}:") and end and f.get("column") != end.strftime("%d.%m.%Y"):
                    bad.append(f"{f['id']} column {f.get('column')}")
        rec.check("A", "A8 period mismatches", f"{sym}: each quarter's figures come from that quarter's column", not bad, "; ".join(bad[:3]), severity="critical")
    mism = [x for x in reps["KAVERI"]["rejections"] if "match" in str(x).lower() or "name" in str(x).lower()]
    rec.check("A", "A8 period mismatches", "KAVERI: filing from a different company rejected", bool(mism), str(mism[:1])[:300], severity="critical")
    kb = {f.get("basis") for f in reps["KAVERI"]["facts"].values() if f["id"].startswith("r:pl:Q")}
    rec.check("A", "A8 period mismatches", "KAVERI: P&L series uses one basis (no standalone/consolidated mixing)", len(kb - {None}) == 1, str(kb), severity="critical")
    # Wrong column order: header dates not in SEBI order must not be read as the current quarter.
    rows = [("1", "Revenue from operations", ["100.00", "110.00", "90.00", "210.00", "180.00", "400.00"]),
            ("2", "Profit before tax", ["10.00", "11.00", "9.00", "21.00", "18.00", "40.00"]),
            ("3", "Net profit for the period", ["8.00", "9.00", "7.00", "17.00", "14.00", "30.00"])]
    pdf = RF.Pdf(rupee=False)
    p = pdf.page(landscape=True)
    pdf.text(p, (36, 44), "Edgecase Industries Limited", 11)
    pdf.text(p, (36, 60), "Statement of Unaudited Financial Results for the quarter ended 30 September 2026", 9)
    pdf.text(p, (36, 74), "(Rs. in crore)", 7.5)
    RF._table(pdf, p, 100, ["Quarter ended"] * 3 + ["Half year ended"] * 2 + ["Year ended"],
              ["30.06.2026", "30.09.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"], rows)
    with tempfile.TemporaryDirectory() as dd:
        f = Path(dd) / "x.pdf"
        pdf.save(f)
        st = S.parse(f.read_bytes(), is_financial=False)
    v = (st.pnl.get("Q2 FY27") or {}).get("revenue")
    rec.check("A", "A8 period mismatches", "columns out of SEBI order: Q2 FY27 revenue read from the 30.09.2026 column (110), or the filing rejected",
              st.status == "failed" or (v is not None and v.value == 110.0), f"status={st.status} reason={st.reason} Q2FY27 revenue={v and v.value}", severity="critical")
