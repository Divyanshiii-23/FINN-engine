"""Claim classification: explicit guidance vs commentary, and never a number from vague words."""

from __future__ import annotations

from datetime import date

import pytest

from finn_engine.research import claims as C
from finn_engine.research.claims import resolve_period


def classify(s: str, *, call="Q4 FY26", on=date(2026, 5, 2), fin=False, it=False, segments=(), role="management", question=None, threads=None):
    return C.classify(s, doc_id="d", doc_kind="transcript", call_period=call, call_date=on, page=1, section="Prepared remarks", speaker="X", role=role,
                      prev_sentence=None, question=question, threads=threads or set(), is_financial=fin, is_it=it, segments=list(segments))


def one(s: str, **kw):
    out = classify(s, **kw)
    assert len(out) == 1, [(c.kind, c.metric) for c in out]
    return out[0]


@pytest.mark.parametrize("s", [
    "We expect revenue to grow in high single digits in FY27.",
    "We expect mid-teens revenue growth in FY27.",
    "We remain confident of delivering healthy growth this year.",
    "We expect strong growth in FY27.",
])
def test_vague_quantities_never_become_numbers(s):
    c = one(s)
    assert c.kind == "guidance" and c.target is not None
    assert c.target.kind == "words" and c.target.low is None and c.target.high is None
    assert not c.explicit
    assert "doesn't turn it into a range" in c.target.reading


def test_double_digit_is_read_literally_and_marked_explicit():
    c = one("For FY27, we are guiding to double-digit revenue growth.")
    assert (c.target.kind, c.target.low, c.target.high) == ("floor", 10, None)
    assert c.explicit and "literally" in c.target.reading


@pytest.mark.parametrize("s,kind,lo,hi,unit", [
    ("We expect EBITDA margin of 24% to 25% for FY27.", "range", 24, 25, "pct"),
    ("Our capex for FY27 will be around Rs. 1,200 crore.", "point", 1140, 1260, "cr"),
    ("We aim to bring net debt below Rs. 1,500 crore by March 2027.", "ceiling", None, 1500, "cr"),
    ("We expect credit cost for FY27 to be in the range of 1.8% to 2.0%.", "range", 1.8, 2.0, "pct"),
    ("We expect EBITDA margins to expand by 100 to 150 bps in FY27.", "delta", 1.0, 1.5, "pp"),
])
def test_explicit_targets(s, kind, lo, hi, unit):
    c = one(s, fin="credit" in s)
    assert c.kind == "guidance" and c.explicit
    assert (c.target.kind, c.target.unit) == (kind, unit)
    assert (c.target.low, c.target.high) == (lo, hi)
    assert c.period == "FY27"


def test_constant_currency_wins_over_revenue():
    c = one("For FY27, we expect revenue growth of 8% to 10% in constant currency terms.", it=True)
    assert c.metric == "revenue_growth_cc"


def test_two_bases_in_one_sentence_become_two_assertions():
    out = classify("Revenue for the quarter grew 1.8% sequentially and 8.2% year-on-year in rupee terms.", call="Q3 FY26", it=True)
    got = sorted((c.basis_hint, c.target.low) for c in out)
    assert got == [("qoq", 1.8), ("yoy", 8.2)]


def test_share_of_book_is_not_growth():
    assert classify("About 18% of the loan book is unsecured personal loans.", fin=True) == []


def test_direction_must_attach_to_the_metric():
    c = one("Margins this quarter absorbed the annual wage increase.", it=True)
    assert c.kind == "outlook"


def test_past_clause_keeps_sentence_period():
    out = classify("FY26 revenue grew 12% with EBITDA margin within our guidance.")
    a = next(c for c in out if c.kind == "assertion")
    assert (a.metric, a.period, a.target.low) == ("revenue", "FY26", 12)
    assert all(c.kind != "guidance" for c in out)


def test_foreign_currency_is_not_rupees():
    c = one("Deal wins of USD 410 million total contract value were signed.", it=True)
    assert c.target is None or c.target.unit != "cr"


def test_withdrawal_and_reaffirmation():
    w = one("Given the uncertainty, we will not be giving credit cost guidance going forward.", fin=True)
    assert w.withdraws and w.metric == "credit_cost"
    r = one("We maintain our EBITDA margin guidance of 18% to 19% for the year.")
    assert r.kind == "guidance" and r.period == "FY27" and r.target.low == 18  # a May 2026 call: "the year" is FY27


def test_analysts_and_moderator_make_no_claims():
    assert classify("Do you still expect 24% to 25% margins for FY27?", role="analyst") == []
    assert classify("We expect 24% margins in FY27.", role="moderator") == []


def test_forward_looking_without_a_period_is_commentary():
    c = one("We will update the margin outlook once remediation costs are clearer.")
    assert c.kind == "outlook" and c.target is None


@pytest.mark.parametrize("text,expected", [
    ("by March 2027", "FY27"), ("in FY27", "FY27"), ("for the full year", "FY26"), ("in the second half", "H2 FY26"),
    ("next quarter", "Q4 FY26"), ("over the next three years", "FY28"), ("in 2026-27", "FY27"),
])
def test_periods(text, expected):
    assert resolve_period(f"We expect revenue growth of 10% {text}.", date(2026, 2, 1), "Q3 FY26")[0] == expected


def test_tone_handles_negation_and_regulatory_words():
    assert C.tone_of("We saw no stress in the portfolio.") == "positive"
    assert C.tone_of("We received a warning letter for our plant.") == "negative"
