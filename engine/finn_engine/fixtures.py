"""Synthetic test fixtures.

Builds BSE-format announcement rows, an NSE-format copy (to exercise cross-
exchange de-duplication), end-of-day price files and a results PDF for the
fictional companies in fixtures/universe.yaml.

Every row carries "_FINN_SYNTHETIC_FIXTURE": true, every document is stamped
SYNTHETIC TEST DOCUMENT, codes are in a range BSE does not use, and no fixture
links to a real exchange URL. The resulting feed is labelled dataset="fixture".
"""

from __future__ import annotations

import csv
import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pymupdf

from .config import load

FIXTURE_AS_OF = "2026-11-04T07:30:00+05:30"
FIXTURE_FROM = date(2026, 10, 25)
FIXTURE_TO = date(2026, 11, 4)
EOD_END = date(2026, 11, 3)
NS = uuid.UUID("6b1f4a40-0000-4000-8000-000000000f17")

# (symbol, "MM-DD HH:MM", subject, headline, subcategory, attachment, attachment_size)
FILINGS: list[tuple] = [
    ("KESTREL", "10-27 18:00", "Board Meeting Intimation for Consideration of Financial Results", "Board meeting on 3 November 2026 to consider unaudited financial results", "Board Meeting", None, None),
    ("KESTREL", "11-03 19:02", "Outcome of Board Meeting", "Board approved the unaudited financial results for the quarter ended 30 September 2026", "Outcome of Board Meeting", None, None),
    ("KESTREL", "11-03 19:12", "Financial Results for the Quarter Ended 30 September 2026", "Unaudited consolidated and standalone financial results for the quarter ended 30.09.2026", "Financial Results", "KESTREL_Q2FY27_results.pdf", 214532),
    ("KESTREL", "11-03 19:13", "Financial Results for the Quarter Ended 30 September 2026", "Unaudited consolidated and standalone financial results for the quarter ended 30.09.2026", "Financial Results", "KESTREL_Q2FY27_results.pdf", 214532),
    ("KESTREL", "11-03 19:20", "Press Release", "Press release on financial results for the quarter ended 30 September 2026", "Press Release", None, None),
    ("KESTREL", "11-03 19:31", "Investor Presentation", "Investor presentation for Q2 FY27", "Investor Presentation", None, None),
    ("KESTREL", "11-03 21:40", "Corrigendum to Financial Results", "Corrigendum: typographical correction in the segment note of the financial results", "Financial Results", None, None),
    ("KESTREL", "11-04 07:05", "Newspaper Publication", "Copy of newspaper publication of financial results", "Newspaper Publication", None, None),
    ("SARANG", "11-03 14:05", "Credit Rating", "The rating agency has revised the long-term rating of the Company from AA- (Stable) to A+ (Negative), a downgrade", "Credit Rating", None, None),
    ("TIDEMARK", "11-03 21:24", "Resignation of Chief Financial Officer", "Mr. S. Kulkarni has resigned as Chief Financial Officer with effect from 30 November 2026", "Resignation", None, None),
    ("TIDEMARK", "11-03 21:31", "Appointment of Chief Financial Officer and Key Managerial Personnel", "Ms. Radhika Menon appointed as Chief Financial Officer with effect from 1 December 2026", "Appointment", None, None),
    ("VEDIKA", "11-04 06:48", "Disclosure under Regulation 30 - Receipt of Warning Letter", "The Company has received a warning letter from an overseas regulator for its Unit 2 formulations facility", "Others", None, None),
    ("VEDIKA", "11-03 16:10", "Intimation of Earnings Call", "Earnings conference call for Q2 FY27 on 6 November 2026 at 16:00 IST", "Analyst / Investor Meet", None, None),
    ("VEDIKA", "11-03 19:50", "ESG Report for FY26", "Business Responsibility and Sustainability Report", "Others", None, None),
    ("CORAL", "11-03 20:15", "Disclosure under SEBI SAST - Encumbrance of Shares", "Promoter has created a pledge; total encumbered shares 18.50% of promoter holding (previous disclosure 14.30%)", "SAST", None, None),
    ("CORAL", "11-03 19:15", "Intimation of Loss of Share Certificate", "Loss of share certificate reported by a shareholder", "Reg. 39 (3) - Details of Loss of Certificate / Duplicate Certificate", None, None),
    ("KAVERI", "11-03 18:55", "Outcome of Board Meeting - Capacity Expansion", "Board approved capex of Rs. 1,150 crore for a 3 MTPA grinding unit in Odisha", "Outcome of Board Meeting", None, None),
    ("HALCYON", "11-03 19:40", "Disclosure under SEBI (Prohibition of Insider Trading) Regulations, 2015", "Promoter group acquired equity shares worth Rs. 12 crore in the open market", "Insider Trading", None, None),
    ("HALCYON", "11-03 14:12", "Compliance Certificate under Regulation 74(5) of SEBI (DP) Regulations", "Certificate for the quarter ended 30 September 2026", "Compliances", None, None),
    ("AURELIA", "11-03 17:30", "Corporate Action - Declaration of Interim Dividend", "Interim dividend of Rs. 6 per equity share; record date 14 November 2026", "Dividend", None, None),
    ("AURELIA", "11-03 13:40", "Schedule of Analyst / Institutional Investor Meetings", "Meetings with institutional investors on 5 and 6 November 2026", "Analyst / Investor Meet", None, None),
    ("QUANTA", "11-03 11:20", "Press Release - Order Win", "The Company bags an order worth Rs. 410 crore for telecom equipment assemblies", "Press Release", None, None),
    ("QUANTA", "11-03 15:02", "Allotment of Equity Shares under ESOP Scheme", "Allotment of 12,400 equity shares under the employee stock option scheme", "Allotment of Equity Shares", None, None),
    ("LOTUS", "11-02 18:00", "Financial Results for the Quarter Ended 30 September 2026", "Unaudited financial results for the quarter ended 30.09.2026", "Financial Results", "LOTUS_Q2FY27_results.pdf", 188210),
    ("LOTUS", "11-03 18:10", "Transcript of Earnings Call", "Transcript of the Q2 FY27 earnings call", "Analyst / Investor Meet", None, None),
    ("HELIX", "10-30 17:45", "Acquisition", "Agreement to acquire 100% stake in a regional diagnostics chain for Rs. 210 crore", "Acquisition", None, None),
    ("HELIX", "11-03 16:55", "Audio Recording of Earnings Call", "Audio recording of the Q2 FY27 earnings call", "Analyst / Investor Meet", None, None),
    ("ORBIT", "10-30 16:40", "Financial Results for the Quarter Ended 30 September 2026", "Unaudited financial results for the quarter ended 30.09.2026", "Financial Results", None, None),
    ("ORBIT", "11-04 07:05", "Proceedings of Extra-ordinary General Meeting", "Proceedings of the EGM held on 3 November 2026", "AGM/EGM", None, None),
    ("MONSOON", "10-29 20:05", "Disclosure of Tax Demand Order", "GST demand order of Rs. 38 crore received; the Company intends to appeal", "Others", None, None),
    ("MONSOON", "11-03 18:22", "Postal Ballot Notice", "Notice of postal ballot and e-voting", "Postal Ballot", None, None),
    ("ANVIL", "10-28 19:10", "Outcome of Board Meeting - Fund Raising", "Board approved raising up to Rs. 600 crore through a QIP", "Outcome of Board Meeting", None, None),
    ("ANVIL", "11-03 16:00", "Closure of Trading Window", "Trading window closed from 1 January 2027", "Trading Window", None, None),
    ("NGRID", "10-29 15:30", "Appointment of Independent Director", "Mr. A. Rao appointed as an Independent Director", "Appointment", None, None),
    ("NGRID", "11-03 14:30", "Intimation regarding change in website address", "The Company's website address will change", "Others", None, None),
    ("MERIDIAN", "11-03 17:05", "Certificate under Regulation 40(9)", "Certificate for the half year ended 30 September 2026", "Compliances", None, None),
]

# A filing whose filer name does not match: must be rejected by the name guard.
MISMATCH = ("TIDEMARK", "11-03 12:00", "Outcome of Board Meeting", "Board approved results", "Outcome of Board Meeting", None, None, "SOME OTHER COMPANY LTD.")

# Latest-session targets: (one-day return, volume / 20-day average)
LAST_SESSION = {
    "SARANG": (-0.042, 2.6),
    "MERIDIAN": (0.068, 3.4),
    "LOTUS": (-0.056, 1.9),
    "QUANTA": (0.039, 1.7),
    "KESTREL": (0.004, 1.1),
}
SPLIT = ("ANVIL", date(2026, 10, 15), 2.0)  # 1:2 split
NO_EOD = {"HELIX"}  # exercises "prices unavailable"
NO_BSE_FILE = {"PRAGATI"}  # exercises "source unavailable"


def _row(code: str, name: str, at: str, subject: str, headline: str, subcat: str, att: str | None, size: int | None, filer: str | None = None) -> dict:
    md, hm = at.split(" ")
    ts = f"2026-{md}T{hm}:00.00"
    nid = str(uuid.uuid5(NS, f"{code}|{at}|{subject}|{headline}"))
    return {
        "_FINN_SYNTHETIC_FIXTURE": True,
        "NEWSID": nid,
        "SCRIP_CD": int(code),
        "NEWSSUB": f"{(filer or name).upper()} - {code} - {subject}",
        "DT_TM": ts,
        "NEWS_DT": ts,
        "DissemDT": ts,
        "HEADLINE": headline,
        "SUBCATNAME": subcat,
        "CATEGORYNAME": None,
        "ATTACHMENTNAME": att or "",
        "Fld_Attachsize": size,
        "SLONGNAME": (filer or name).upper(),
        "NSURL": None,
    }


def _trading_days(end: date, n: int) -> list[date]:
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _eod(symbol: str, out: Path) -> None:
    rnd = random.Random(f"finn-fixture-{symbol}")
    days = _trading_days(EOD_END, 130)
    price = 200 + rnd.random() * 2500
    vol0 = int(2e5 + rnd.random() * 1.5e6)
    adj, vols = [], []
    for _ in days:
        price *= 1 + (rnd.random() - 0.49) * 0.03
        adj.append(price)
        vols.append(int(vol0 * (0.7 + rnd.random() * 0.6)))
    if symbol in LAST_SESSION:
        r, v = LAST_SESSION[symbol]
        adj[-1] = adj[-2] * (1 + r)
        vols[-1] = int(sum(vols[-21:-1]) / 20 * v)
    raw = list(adj)
    split_dates: list[date] = []
    if symbol == SPLIT[0]:
        _, sd, ratio = SPLIT
        raw = [a * ratio if d < sd else a for a, d in zip(adj, days)]
        split_dates.append(sd)
    with (out / f"{symbol}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])
        for d, c, a, v in zip(days, raw, adj, vols):
            w.writerow([d.isoformat(), round(c * 0.995, 2), round(c * 1.01, 2), round(c * 0.985, 2), round(c, 2), round(a, 2), v])
    if split_dates:
        (out / f"{symbol}.splits").write_text("\n".join(d.isoformat() for d in split_dates))


def results_pdf(path: Path) -> None:
    """Two-page SEBI-style results statement (standalone, then consolidated), in lakhs."""
    doc = pymupdf.open()
    cols = [300, 360, 420, 480, 540]
    header_dates = ["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "30.09.2025"]
    def page(title: str, rows: list[tuple[str, str, list[str]]]) -> None:
        p = doc.new_page(width=595, height=842)
        p.insert_text((40, 40), "SYNTHETIC TEST DOCUMENT - not a real filing. Kestrel Polymers is a fictional company.", fontsize=8, color=(0.6, 0, 0))
        p.insert_text((40, 62), "Kestrel Polymers Limited", fontsize=11)
        p.insert_text((40, 78), title, fontsize=9)
        p.insert_text((40, 92), "(Rs. in lakhs, except per share data)", fontsize=8)
        p.insert_text((cols[0] - 22, 110), "Quarter ended", fontsize=7)
        p.insert_text((cols[3] - 26, 110), "Half year ended", fontsize=7)
        for x, d in zip(cols, header_dates):
            w = pymupdf.get_text_length(d, fontsize=7)
            p.insert_text((x - w / 2, 122), d, fontsize=7)
        y = 142
        for serial, label, vals in rows:
            p.insert_text((40, y), serial, fontsize=7.5)
            p.insert_text((62, y), label, fontsize=7.5)
            for x, v in zip(cols, vals):
                w = pymupdf.get_text_length(v, fontsize=7.5)
                p.insert_text((x - w / 2, y), v, fontsize=7.5)
            y += 15
    def table(scale: float) -> list[tuple[str, str, list[str]]]:
        def f(*xs: float) -> list[str]:
            return [f"{x * scale:,.2f}" if x != 0 else "-" for x in xs]
        return [
            ("I", "Revenue from operations", f(128462, 123604, 115130, 252066, 225530)),
            ("II", "Other income", f(850, 790, 710, 1640, 1390)),
            ("III", "Total income (I+II)", f(129312, 124394, 115840, 253706, 226920)),
            ("IV", "Expenses", []),
            ("(a)", "Cost of materials consumed", f(70210, 66980, 62140, 137190, 121880)),
            ("(b)", "Employee benefits expense", f(9820, 9640, 8900, 19460, 17600)),
            ("(c)", "Finance costs", f(1420, 1380, 1240, 2800, 2450)),
            ("(d)", "Depreciation and amortisation expense", f(5260, 5190, 4930, 10450, 9700)),
            ("(e)", "Other expenses", f(30454, 28302, 26810, 58756, 52390)),
            ("", "Total expenses", f(117164, 111492, 104020, 228656, 204020)),
            ("V", "Profit before exceptional items and tax (III-IV)", f(12148, 12902, 11820, 25050, 22900)),
            ("VI", "Exceptional items", f(0, 0, 0, 0, 0)),
            ("VII", "Profit before tax (V-VI)", f(12148, 12902, 11820, 25050, 22900)),
            ("VIII", "Tax expense", []),
            ("(a)", "Current tax", f(2900, 3020, 2780, 5920, 5400)),
            ("(b)", "Deferred tax", f(242, 251, 238, 493, 460)),
            ("", "Total tax expense", f(3142, 3271, 3018, 6413, 5860)),
            ("IX", "Net Profit for the period (VII-VIII)", f(9006, 9631, 8802, 18637, 17040)),
            ("X", "Other comprehensive income", f(-40, 25, 12, -15, 30)),
            ("XI", "Total comprehensive income for the period", f(8966, 9656, 8814, 18622, 17070)),
            ("", "Profit attributable to owners of the Company", f(9006, 9631, 8802, 18637, 17040)),
        ]
    page("Statement of Unaudited Standalone Financial Results for the quarter ended 30 September 2026", table(0.93))
    page("Statement of Unaudited Consolidated Financial Results for the quarter ended 30 September 2026", table(1.0))
    doc.save(path)


def build(engine_dir: Path, out: Path) -> Path:
    cfg = load(engine_dir / "fixtures" / "universe.yaml")
    for sub in ("bse", "nse", "eod", "attachments"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    by_symbol: dict[str, list[dict]] = {}
    for sym, at, subject, headline, subcat, att, size in FILINGS:
        c = cfg.company(sym)
        by_symbol.setdefault(sym, []).append(_row(c.bse_code or "", c.name, at, subject, headline, subcat, att, size))
    sym, at, subject, headline, subcat, att, size, filer = MISMATCH
    c = cfg.company(sym)
    by_symbol[sym].append(_row(c.bse_code or "", c.name, at, subject, headline, subcat, att, size, filer=filer))
    for c in cfg.companies:
        if c.symbol not in NO_EOD:
            _eod(c.symbol, out / "eod")
        if c.symbol in NO_BSE_FILE:
            continue
        rows = by_symbol.get(c.symbol, [])
        (out / "bse" / f"{c.symbol}.json").write_text(json.dumps({"_FINN_SYNTHETIC_FIXTURE": True, "Table": rows, "Table1": [{"ROWCNT": len(rows)}]}, indent=1))
    # NSE-format copy of the Kestrel results filing, one minute later.
    (out / "nse" / "KESTREL.json").write_text(json.dumps([{
        "_FINN_SYNTHETIC_FIXTURE": True,
        "symbol": "KESTREL",
        "seq_id": "fixture-nse-0001",
        "desc": "Financial Results",
        "attchmntText": "Unaudited consolidated and standalone financial results for the quarter ended 30.09.2026",
        "sort_date": "2026-11-03 19:14:05",
        "attchmntFile": "KESTREL_Q2FY27_results_nse.pdf",
        "sm_name": "Kestrel Polymers Limited",
    }], indent=1))
    results_pdf(out / "attachments" / "KESTREL_Q2FY27_results.pdf")
    # LOTUS_Q2FY27_results.pdf is deliberately absent: exercises "attachment unavailable".
    return out


def as_of() -> datetime:
    return datetime.fromisoformat(FIXTURE_AS_OF)
