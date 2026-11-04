"""Ask FINN: answers from the company's documents only, every block cited and checked."""

from __future__ import annotations

import json
import re

import pytest

from finn_engine.research import fixtures as RF
from finn_engine.research.ask import Index, answer, intent_of, toks, validate
from finn_engine.research.pipeline import run, write
from finn_engine.research.sources import FileInputs


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("ask")
    RF.build(root / "in")
    inp = FileInputs(root / "in")
    out = {}
    for s in ("HALCYON", "KAVERI", "SARANG", "VEDIKA", "CORAL"):
        rep = run(s, inp, as_of=RF.AS_OF)
        write(rep, root / "out")
        out[s] = (json.loads((root / "out" / f"{s}.json").read_text()), json.loads((root / "out" / f"{s}.passages.json").read_text()))
    return out


def ask(built, sym: str, q: str, **kw) -> dict:
    rep, ps = built[sym]
    return answer(q, rep, ps, **kw)


def cited_docs(ans: dict, rep: dict) -> set[str]:
    """Documents behind an answer, following computed figures back to the filings they came from."""
    docs = {d["id"]: d for d in rep["documents"]}
    out, seen = set(), set()
    stack = [c for b in ans["blocks"] for c in b["cites"]]
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        f = rep["facts"].get(c) or {}
        d = (ans["passages"].get(c) or {}).get("doc_id") or f.get("doc_id")
        if d:
            out.add(f"{docs[d]['kind']}:{docs[d]['period']}")
        stack += f.get("inputs", [])
    return out


def all_supported(ans: dict, rep: dict) -> None:
    for b in ans["blocks"]:
        assert validate(b, rep, ans["passages"], ans["question"], strict=False) is None, b
        if b["kind"] in ("fact", "management", "guidance", "finding", "interpretation", "table"):
            assert b["cites"], b


# ------------------------------------------------------------------ passages and retrieval

def test_passages_cover_every_kind_with_location(built):
    rep, ps = built["KAVERI"]
    kinds = {p["doc_kind"] for p in ps}
    assert kinds == {"results", "transcript", "presentation", "annual_report"}
    assert all(p["page"] >= 1 and p["doc_id"] for p in ps)
    tr = [p for p in ps if p["doc_kind"] == "transcript"]
    assert all(p["role"] in ("management", "analyst") and p["speaker"] for p in tr)
    qa = [p for p in tr if p["section"] == "Q&A" and p["role"] == "management"]
    assert qa and all(p.get("question") for p in qa)  # answers carry the question they answer
    tables = [p for p in ps if p.get("table")]
    assert any("Cash Flows" in p["section"] for p in tables)
    assert not any("Kaveri Roadways" in p["text"] for p in ps)  # rejected filings are never indexed


def test_bm25_ranks_specific_terms():
    ix = Index([{"text": "Fuel costs were higher in the quarter."}, {"text": "Demand was healthy."}, {"text": "Fuel and power costs eased."}])
    hits = ix.search(toks("fuel costs higher"), min_score=0.1)
    assert hits[0][1]["text"].startswith("Fuel costs were higher")


@pytest.mark.parametrize("q,intent", [
    ("Why did margins decline?", "explain_change"), ("What changed between the last two earnings calls?", "call_diff"),
    ("Is operating cash flow supporting reported profits?", "cash_vs_profit"), ("What did management promise regarding capacity expansion?", "promises"),
    ("Which financial indicators contradict management's narrative?", "contradictions"), ("What did management say about client spending?", "said_about"),
    ("Should I buy the stock?", "out_of_scope"), ("What is the target price?", "out_of_scope"),
])
def test_intents(q, intent):
    assert intent_of(q) == intent


# ------------------------------------------------------------------ the five example questions

def test_why_margins_declined(built):
    rep, _ = built["KAVERI"]
    a = ask(built, "KAVERI", "Why did margins decline?")
    assert a["status"] == "answered"
    facts = [b for b in a["blocks"] if b["kind"] == "fact"]
    assert "13.8%" in facts[0]["text"] and "16.8%" in facts[0]["text"] and "-3.0 pp" in facts[0]["text"]
    assert any("other expenses" in b["text"] and "c:Q2FY27:share_chg:other_exp:Q2FY26" in b["cites"] for b in facts)  # cost-line split, as cited facts
    mg = next(b for b in a["blocks"] if b["kind"] == "management")
    texts = " ".join(a["passages"][c]["text"] for c in mg["cites"])
    assert "Realisations came under pressure" in texts and "Fuel costs were higher" in texts
    assert all(a["passages"][c]["period"] == "Q2 FY27" for c in mg["cites"])
    assert any(b["kind"] == "interpretation" and "resilient" not in b["text"] and "described margins positively" in b["text"] for b in a["blocks"])
    assert any("doesn't add causes" in b["text"] for b in a["blocks"])  # the why is management's, not FINN's
    all_supported(a, rep)


def test_what_changed_between_calls(built):
    rep, _ = built["KAVERI"]
    a = ask(built, "KAVERI", "What changed between the last two earnings calls?")
    g = next(b for b in a["blocks"] if b["kind"] == "fact" and b["text"].startswith("Guidance"))
    assert "EBITDA margin FY27: not repeated (was 18–19% on the Q1 FY27 call)" in g["text"]
    assert any("Pricing: tone went from positive on the Q1 FY27 call to negative on the Q2 FY27 call" in b["text"] for b in a["blocks"])
    assert {"transcript:Q1 FY27", "transcript:Q2 FY27", "results:Q2 FY27"} <= cited_docs(a, rep)  # Q1 FY27 figures as reprinted in the Q2 filing
    h = ask(built, "HALCYON", "What changed between the last two earnings calls?")
    assert any("EBIT margin FY27: lowered 20–21% (was 21–22% on the Q1 FY27 call)" in b["text"] for b in h["blocks"])  # cut in the deck, repeated on the call
    all_supported(a, rep)
    v = ask(built, "VEDIKA", "What changed between the last two earnings calls?")
    assert any(b["kind"] == "gap" and "No Q1 FY27 call transcript" in b["text"] for b in v["blocks"])


def test_cash_supporting_profit(built):
    rep, _ = built["KAVERI"]
    a = ask(built, "KAVERI", "Is operating cash flow supporting reported profits?")
    assert {"results:Q4 FY25", "results:Q4 FY26", "results:Q2 FY27"} <= cited_docs(a, rep)  # FY24 comes from the Q4 FY25 filing
    years = next(b for b in a["blocks"] if b["text"].startswith("Operating cash flow by year"))
    assert "FY24" in years["text"] and "FY26" in years["text"]
    assert any("free cash flow was −₹153.8 cr" in b["text"] for b in a["blocks"])
    assert any(b["kind"] == "interpretation" and "less clear for the current year" in b["text"] for b in a["blocks"])
    assert any("described cash generation positively" in b["text"] for b in a["blocks"])
    lender = ask(built, "SARANG", "Is operating cash flow supporting reported profits?")
    assert lender["status"] == "insufficient" and "loan book" in lender["blocks"][0]["text"]


def test_capacity_promises_span_documents_and_years(built):
    rep, _ = built["KAVERI"]
    a = ask(built, "KAVERI", "What did management promise regarding capacity expansion?")
    g = [b for b in a["blocks"] if b["kind"] == "guidance"]
    assert [re.search(r"for (\S+ ?FY\d\d|FY\d\d)", b["text"]).group(1) for b in g if b["text"].startswith("Capex")] == ["FY25", "FY26", "FY27"]
    fy25 = next(b for b in g if b["text"].startswith("Capex for FY25"))
    assert "as ~₹1,100 cr" in fy25["text"] and "delivered" in fy25["text"]
    docs = cited_docs(a, rep)
    assert {"transcript:Q1 FY25", "transcript:Q3 FY25", "transcript:Q4 FY25", "annual_report:FY25", "annual_report:FY26"} <= docs
    extra = next(b for b in a["blocks"] if b["kind"] == "management")
    assert any("commissioning" in a["passages"][c]["text"] for c in extra["cites"])
    all_supported(a, rep)


def test_contradictions(built):
    rep, _ = built["KAVERI"]
    a = ask(built, "KAVERI", "Which financial indicators contradict management's narrative?")
    rules = [b.get("rule") for b in a["blocks"] if b["kind"] == "finding"]
    assert rules[:3] == ["commentary_vs_numbers"] * 3
    assert all(len(b["cites"]) >= 2 for b in a["blocks"] if b["kind"] == "finding")  # a quote and a figure
    h = ask(built, "HALCYON", "Which financial indicators contradict management's narrative?")
    assert not any(b.get("rule") == "commentary_vs_numbers" for b in h["blocks"])
    v = ask(built, "VEDIKA", "Which indicators contradict what management said?")
    assert {"assertion_contradicted", "documents_disagree"} <= {b.get("rule") for b in v["blocks"]}


# ------------------------------------------------------------------ more periods, other sectors

def test_theme_across_many_calls(built):
    rep, _ = built["HALCYON"]
    a = ask(built, "HALCYON", "What did management say about client spending?")
    calls = [b["text"].split(" call")[0] for b in a["blocks"] if b["kind"] == "management"]
    assert len(calls) >= 6 and calls[0] == "Q1 FY25" and calls[-1] == "Q2 FY27"
    assert any("turned negative between the Q4 FY26 and Q2 FY27 calls" in b["text"] for b in a["blocks"] if b["kind"] == "interpretation")
    assert a["status"] == "answered"


def test_lender_asset_quality(built):
    a = ask(built, "SARANG", "How has asset quality changed?")
    assert a["blocks"][0]["text"].startswith("Credit cost") and "FY25" in a["blocks"][0]["text"]
    assert any("turned negative between the Q1 FY27 and Q2 FY27" in b["text"] for b in a["blocks"])


def test_false_premise_is_corrected(built):
    a = ask(built, "HALCYON", "Why did revenue fall?")
    assert any(b["kind"] == "note" and "assumes revenue fell" in b["text"] for b in a["blocks"])
    assert a["status"] == "answered"


# ------------------------------------------------------------------ refusing and saying "not enough"

@pytest.mark.parametrize("q", ["What is the CEO's salary?", "How many employees work in the Pune office?", "What is the company's market share in Kerala?"])
def test_insufficient_evidence_is_said(built, q):
    a = ask(built, "KAVERI", q)
    assert a["status"] in ("insufficient", "partial")
    if a["status"] == "insufficient":
        assert "don't address" in a["blocks"][-1]["text"] and "10 call transcripts" in a["blocks"][-1]["text"]


@pytest.mark.parametrize("q", ["Should I buy this stock?", "What is a fair value for the shares?", "Who won the world cup?"])
def test_out_of_scope(built, q):
    a = ask(built, "KAVERI", q)
    assert a["status"] == "out_of_scope" and not a["passages"]


def test_company_without_documents(built):
    a = ask(built, "CORAL", "Why did margins decline?")
    assert a["status"] == "insufficient"


def test_every_answer_is_supported(built):
    qs = ["Why did margins decline?", "What changed between the last two earnings calls?", "Is operating cash flow supporting reported profits?",
          "What did management promise regarding capacity expansion?", "Which financial indicators contradict management's narrative?", "What did management say about demand?",
          "How has revenue moved over time?", "What is the outlook for margins?"]
    for sym in ("HALCYON", "KAVERI", "SARANG", "VEDIKA"):
        rep, _ = built[sym]
        for q in qs:
            a = ask(built, sym, q)
            all_supported(a, rep)
            assert a["method"] == "rules"


# ------------------------------------------------------------------ the validator, and an optional model

def test_validator_rejects_numbers_not_in_evidence(built):
    rep, _ = built["KAVERI"]
    blk = {"kind": "fact", "text": "EBITDA margin was 13.8% in Q2 FY27, down 9.9 pp.", "cites": ["c:Q2FY27:ebitda_margin"]}
    assert "9.9" in validate(blk, rep, {}, "", strict=False)
    assert validate({"kind": "fact", "text": "x", "cites": ["c:nope"]}, rep, {}, "", strict=False).startswith("cites unknown")


def fake(text: str):
    return lambda prompt: text


def test_model_answer_accepted_only_when_grounded(built):
    rep, ps = built["KAVERI"]
    rules = ask(built, "KAVERI", "Why did margins decline?")
    m_id = "c:Q2FY27:ebitda_margin"
    pid = next(c for b in rules["blocks"] if b["kind"] == "management" for c in b["cites"])
    good = json.dumps({"blocks": [
        {"kind": "fact", "text": "EBITDA margin was 13.8% in Q2 FY27.", "cite": [m_id]},
        {"kind": "management", "text": "Management said realisations came under pressure in the southern markets.", "cite": [pid]},
    ]})
    a = answer("Why did margins decline?", rep, ps, complete=fake(good), model="test")
    assert a["method"].startswith("model") and len(a["blocks"]) == 2
    bad = json.dumps({"blocks": [
        {"kind": "fact", "text": "EBITDA margin was 11.2% in Q2 FY27.", "cite": [m_id]},  # number not in evidence
        {"kind": "fact", "text": "Cement prices across India fell because of a national oversupply cycle.", "cite": [m_id]},  # general knowledge
        {"kind": "interpretation", "text": "The company is poorly managed.", "cite": []},  # uncited
    ]})
    b = answer("Why did margins decline?", rep, ps, complete=fake(bad), model="test")
    assert b["method"] == "rules" and "model_rejected" in b
    broken = answer("Why did margins decline?", rep, ps, complete=fake("not json"), model="test")
    assert broken["method"] == "rules" and "unparseable" in broken["model_rejected"]


def test_model_never_called_for_insufficient_or_out_of_scope(built):
    rep, ps = built["KAVERI"]
    calls = []
    def spy(p):
        calls.append(p)
        return "{}"
    answer("What is the CEO's salary?", rep, ps, complete=spy, model="t")
    answer("Should I buy?", rep, ps, complete=spy, model="t")
    assert calls == []
