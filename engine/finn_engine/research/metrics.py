"""Metric registry: which management metrics FINN can check, and how.

`source` says where the actual comes from. Metrics whose actual is not in
the filed financial statements are still extracted and shown, but their
verdict is "unverifiable" with the reason below. They are never estimated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    pattern: str
    kind: str  # growth | level | amount | days | ratio
    better: str = "up"  # up | down
    tol: float = 0.5  # pp for growth/level, fraction for amount
    unverifiable: str | None = None
    lender: bool | None = None  # True: lenders only; False: non-lenders only; None: both


METRICS: list[Metric] = [
    # Checked against reported statements.
    Metric("revenue_growth_cc", "Revenue growth (constant currency)", r"constant currency|\bcc\b|in dollar terms|usd terms|dollar revenue", "growth",
           unverifiable="Constant-currency growth isn't in the filed rupee statements; FINN doesn't read the company's currency mix."),
    Metric("ebit_margin", "EBIT margin", r"\bebit margins?\b|\bebit level", "level"),
    Metric("gross_margin", "Gross margin", r"gross margins?", "level", lender=False),
    Metric("pat_margin", "PAT margin", r"\b(pat|net profit|net) margins?\b", "level"),
    Metric("nim", "Net interest margin", r"\bnims?\b|net interest margins?", "level", tol=0.25, lender=True,
           unverifiable="Lenders quote NIM on average AUM or earning assets; the statements give only on-book loans, so the two aren't compared."),
    Metric("ebitda_margin", "EBITDA margin", r"ebitda margins?|operating (profit )?margins?|\bmargins?\b", "level"),
    Metric("credit_cost", "Credit cost", r"credit costs?", "level", better="down", tol=0.1, lender=True),
    Metric("gnpa", "Gross NPA / Stage 3", r"\bgnpa\b|gross npa|stage[- ]?3|gross stage", "level", better="down",
           unverifiable="Asset-quality ratios are disclosed in notes and presentations, not the statements FINN reads.", lender=True),
    Metric("aum_growth", "AUM growth", r"\baum\b|assets under management", "growth",
           unverifiable="AUM includes off-book loans; the balance sheet reports on-book loans only.", lender=True),
    Metric("loan_growth", "Loan book growth", r"loan book|loan portfolio|book growth|balance sheet growth", "growth", lender=True),
    Metric("disbursement", "Disbursements", r"disburs", "growth", unverifiable="Disbursements aren't in the financial statements.", lender=True),
    Metric("capex", "Capex", r"\bcapex\b|capital expenditure|capital outlay|investment outlay", "amount", tol=0.05, better="up"),
    Metric("net_debt", "Net debt", r"net[- ]debt|debt[- ]free|deleverag|gross debt|\bdebt\b", "amount", better="down", tol=0.05),
    Metric("wc_days", "Working-capital days", r"working capital (days|cycle)|receivable days|debtor days|inventory days", "days", better="down", tol=0.1),
    Metric("volume_growth", "Volume growth", r"\bvolumes?\b", "growth", unverifiable="Volumes aren't in the financial statements."),
    Metric("exports", "Export revenue", r"\bexports?\b|international business", "growth", unverifiable="The geographic split is disclosed annually, not in quarterly statements."),
    Metric("order_book", "Order book / inflow", r"order (book|inflow|intake|backlog)|\btcv\b|deal wins|total contract value", "amount",
           unverifiable="Orders and deal values aren't in the financial statements."),
    Metric("utilisation", "Utilisation", r"utili[sz]ation", "level", unverifiable="Utilisation isn't in the financial statements."),
    Metric("attrition", "Attrition", r"attrition", "level", better="down", unverifiable="Attrition isn't in the financial statements."),
    Metric("headcount", "Hiring / headcount", r"freshers|headcount|hiring|net adds", "amount", unverifiable="Headcount isn't in the financial statements."),
    Metric("ebitda", "EBITDA", r"\bebitda\b", "growth", lender=False),
    Metric("pat", "Profit after tax", r"\bpat\b|net profit|profit after tax|bottom[- ]?line|\bearnings\b", "growth"),
    Metric("revenue", "Revenue", r"\brevenues?\b|top[- ]?line|\bsales\b|turnover|income from operations|\bgrowth\b", "growth"),
]

BY_ID = {m.id: m for m in METRICS}
GROWTH_QUALIFIERS = {"our", "healthy", "strong", "robust", "good", "decent", "double-digit", "digit", "teens", "steady", "sustainable",
                     "overall", "profitable", "sustained", "consolidated", "organic", "twenties", "single-digit", "mid-teens", "high-teens", "low-teens"}


def find(text: str, is_financial: bool, is_it: bool) -> list[tuple[Metric, int]]:
    """Registry metrics named in text, with position, most specific first."""
    low = text.lower()
    hits: list[tuple[Metric, int]] = []
    taken: list[tuple[int, int]] = []
    for m in METRICS:
        if m.lender is True and not is_financial or m.lender is False and is_financial:
            continue
        for mm in re.finditer(m.pattern, low):
            s, e = mm.span()
            if any(a <= s < b or a < e <= b for a, b in taken):
                continue
            mid = m
            # "Operating margin" and bare "margins" mean EBIT for IT services and NIM for lenders.
            if m.id == "ebitda_margin" and "ebitda" not in mm.group(0):
                mid = BY_ID["ebit_margin"] if is_it else BY_ID["nim"] if is_financial else m
            if m.id == "revenue" and mm.group(0) == "growth":
                # Bare "growth" stands for revenue only after a qualifier ("healthy growth", "double-digit growth").
                prev = re.findall(r"[a-z\-%]+", low[:s])[-1:] or [""]
                if any(h[0].kind == "growth" for h in hits) or prev[0] not in GROWTH_QUALIFIERS and not prev[0].endswith("%"):
                    continue
            hits.append((mid, s))
            taken.append((s, e))
    # "Revenue growth of 8-10% in constant currency" is a constant-currency statement, wherever the words sit.
    cc = next((h for h in hits if h[0].id == "revenue_growth_cc"), None)
    if cc:
        rev = [h for h in hits if h[0].id == "revenue"]
        hits = [h for h in hits if h[0].id != "revenue"]
        if rev:
            hits = [(cc[0], min(r[1] for r in rev)) if h is cc else h for h in hits]
    return sorted(hits, key=lambda h: h[1])
