"""Regressions for defects found by the evaluation suite (eval/EVAL.md). Each test names the eval check it guards."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from finn_engine.classify import classify
from finn_engine.dedupe import dedupe
from finn_engine.extract.facts import amounts_cr, extract_facts
from finn_engine.market import signal_at
from finn_engine.materiality import score
from finn_engine.models import Announcement, Company, EodBar, SourceRef
from finn_engine.research import claims as C
from finn_engine.research.ask import Index, _stem, toks

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 3, 18, 0, tzinfo=IST)
CO = Company(symbol="X", name="X LTD", market_cap_cr=10000, revenue_ttm_cr=4000)


def ann(subject, headline=None, at=T0, source="bse", attachment=None, size=None):
    sid = f"{source}{subject}{headline}{at}{attachment}{random.random()}"
    return Announcement(id=str(abs(hash(sid))), symbol="X", company_on_filing="X LTD", subject=subject, headline=headline, filed_at=at, attachment_size=size,
                        source=SourceRef(source=source, source_id=sid, attachment_url=f"https://www.bseindia.com/x/{attachment}" if attachment else None, fetched_at=datetime.now(timezone.utc)))


def tier(subject, headline):
    a = ann(subject, headline)
    c = classify(a)
    return score(CO, c, extract_facts(c.category, c.subtype, f"{subject} {headline}"), None, None, False).tier


# C2: material events that scored too low before the fixes
def test_share_count_is_not_rupees_and_buyback_size_is_count_times_price():
    assert amounts_cr("invoked the pledge on 1.4 crore shares") == ([], None)
    assert amounts_cr("buyback of up to 1.2 crore equity shares at Rs. 1,500 per share")[0] == [1800.0]
    assert tier("Outcome of Board Meeting - Buyback", "buyback of up to 1.2 crore equity shares at Rs. 1,500 per share") == "interrupt"


def test_senior_exits_defaults_and_searches_interrupt():
    assert tier("Resignation of Chief Executive Officer", "Mr. T. Bose, CEO, has resigned") == "interrupt"
    assert tier("Default in payment of interest on Non-Convertible Debentures", "Delay in payment of interest due on listed NCDs") == "interrupt"
    assert tier("Search operations by Income Tax Department", "Income tax officials conducted search operations") == "interrupt"


def test_nclt_sanctioning_a_merger_is_not_an_insolvency_alert():
    a = ann("NCLT sanctions Scheme of Amalgamation", "The NCLT has sanctioned the scheme of amalgamation")
    assert classify(a).category == "mna"


# C3
def test_generic_subject_with_different_attachments_is_not_a_duplicate():
    a = ann("Announcement under Regulation 30 (LODR)-General", attachment="G1.pdf", size=1)
    b = ann("Announcement under Regulation 30 (LODR)-General", at=T0 + timedelta(minutes=12), attachment="G2.pdf", size=2)
    out = {x.id: x for x in dedupe([a, b])}
    assert out[b.id].duplicate_of is None


def test_exchange_copy_hours_later_is_a_duplicate():
    h = "Board approved the unaudited results for the quarter ended 30 September 2026"
    a = ann("Outcome of Board Meeting", h, attachment="X.pdf")
    b = ann("Outcome of Board Meeting", h, at=T0 + timedelta(hours=2, minutes=10), source="nse")
    out = {x.id: x for x in dedupe([a, b])}
    assert out[b.id].duplicate_of == a.id


# C5
def _bars(n=80, last_vol=None, zero_days=(), split_at=None):
    rnd, d, out, px = random.Random(7), date(2026, 6, 1), [], 100.0
    while len(out) < n:
        if d.weekday() < 5:
            px *= 1 + rnd.gauss(0, 0.012)
            v = int(1_000_000 * rnd.uniform(0.85, 1.15)) * (2 if split_at is not None and len(out) >= split_at else 1)
            v = 0 if len(out) in zero_days else v
            v = last_vol if len(out) == n - 1 and last_vol is not None else v
            out.append(EodBar(date=d, open=px, high=px, low=px, close=px, adj_close=px, volume=v))
        d += timedelta(days=1)
    return out


def test_suspension_days_are_left_out_of_the_volume_baseline():
    s = signal_at("X", _bars(last_vol=2_200_000, zero_days=(70, 72)), set())
    assert 1.9 <= s.vol_ratio_20d <= 2.5


def test_volume_baseline_restarts_after_a_split():
    b = _bars(split_at=70)
    s = signal_at("X", b, {b[70].date})
    assert s.vol_ratio_20d is None and "split" in s.note


# B4
def _claims(s):
    return C.classify(s, doc_id="d", doc_kind="transcript", call_period="Q2 FY27", call_date=date(2026, 10, 29), page=1, section="Prepared remarks", speaker="X",
                      role="management", prev_sentence=None, question=None, threads=set(), is_financial=False, is_it=False, segments=[])


def test_a_price_increase_is_not_a_margin_target():
    assert not [c for c in _claims("Price increases of 3% taken in October should support margins in the second half.") if c.kind == "guidance" and c.explicit]


def test_amount_already_spent_does_not_set_the_period():
    c = [c for c in _claims("Capex this year will be Rs. 600 to 650 crore, of which Rs. 280 crore has been spent in the first half.") if c.explicit]
    assert [(x.period, x.target.low, x.target.high) for x in c] == [("FY27", 600.0, 650.0)]


def test_plus_or_minus_basis_points_is_a_range():
    c = [c for c in _claims("We expect EBITDA margin of 23% plus or minus 50 basis points in FY27.") if c.explicit][0]
    assert (c.target.low, c.target.high) == (22.5, 23.5)


def test_reported_growth_followed_by_vague_outlook_is_not_guidance():
    assert not [c for c in _claims("Our revenue grew 14% in H1, and we expect similar momentum to continue.") if c.kind == "guidance" and c.explicit]


# B1
def test_search_terms_are_not_stemmed_twice():
    ps = [{"text": "Utilisation has room to improve."}, {"text": "Revenue grew."}]
    assert Index(ps).search(toks("workforce utilisation"), min_score=0.1)
    assert _stem("price") == _stem("prices") == _stem("priced")


def test_paraphrase_finds_the_documents_word():
    ps = [{"text": "Freight costs rose because diesel prices went up."}, {"text": "Revenue grew."}]
    hits = Index(ps).search(toks("logistics costs"), min_score=0.1)
    assert hits and "Freight" in hits[0][1]["text"]


# Release check: synthetic fixtures must never use a real listed company's ticker.
def test_no_fixture_symbol_is_a_real_nse_ticker():
    import csv
    from pathlib import Path

    import yaml

    from finn_engine.research import fixtures as RF

    seed = Path(__file__).resolve().parents[1] / "finn_engine/research/seed/nse_equity_list_2023-11-05.csv"
    real = {r["SYMBOL"].strip() for r in csv.DictReader(open(seed))}
    push = {c["symbol"] for c in yaml.safe_load(open(Path(__file__).resolve().parents[1] / "fixtures/universe.yaml"))["companies"]}
    research = {f().symbol for f in RF.COMPANIES} | {"CORAL"}
    assert not (push | research) & real, (push | research) & real
