"""Management credibility: observed, counted and cited, never a composite score."""

from __future__ import annotations

import pytest

from finn_engine.research import fixtures as RF
from finn_engine.research.credibility import MIN_CLOSED, model_rephraser
from finn_engine.research.pipeline import run
from finn_engine.research.sources import FileInputs


@pytest.fixture(scope="module")
def reps(tmp_path_factory):
    root = tmp_path_factory.mktemp("cred")
    RF.build(root / "in")
    inp = FileInputs(root / "in")
    return {s: run(s, inp, as_of=RF.AS_OF) for s in ("HALCYON", "KAVERI", "SARANG", "VEDIKA", "CORAL")}


def ind(rep: dict, iid: str) -> dict:
    return next(i for i in rep["credibility"]["indicators"] if i["id"] == iid)


def rules(rep: dict) -> set[str]:
    return {p["rule"] for p in rep["credibility"]["interpretation"]}


def test_history_window_covers_three_fiscal_years(reps):
    w = reps["KAVERI"]["credibility"]["window"]
    assert (w["calls"], w["first_call"], w["last_call"], w["results"]) == (10, "Q1 FY25", "Q2 FY27", 10)
    assert w["closed_years"] == ["FY25", "FY26"]


def test_no_composite_score_anywhere(reps):
    for r in reps.values():
        c = r["credibility"]
        assert "score" not in c and "no_score" in c["rules"]
        for i in c["indicators"]:
            assert "score" not in i


@pytest.mark.parametrize("sym,kept,n,status", [("HALCYON", 4, 4, "observed"), ("KAVERI", 4, 6, "observed"), ("VEDIKA", 4, 4, "observed"), ("SARANG", 1, 3, "insufficient")])
def test_delivery_counts_and_gate(reps, sym, kept, n, status):
    d = ind(reps[sym], "delivery")
    assert (d["stat"]["kept"], d["n"], d["status"]) == (kept, n, status)
    assert (d["stat"]["rate"] is None) == (n < MIN_CLOSED)
    assert all(r["evidence"] and r["actual"] for r in d["rows"])


def test_insufficient_history_is_said_not_scored(reps):
    s = reps["SARANG"]
    assert "insufficient_history" in rules(s) and "delivery_observed" not in rules(s)
    assert "rate only from 4" in ind(s, "delivery")["headline"]
    assert "repeated_miss_same_metric" in rules(s)  # a pattern on one metric is still stated, with its two observations


def test_landing_sides_respect_metric_direction(reps):
    k = ind(reps["KAVERI"], "landing")
    assert k["stat"] == {"favourable": 0, "at": 1, "adverse": 4}
    cap = next(r for r in k["rows"] if r["metric"] == "Capex" and r["period"] == "FY26")
    assert cap["offset"] == pytest.approx(1020 / 1200 - 1, abs=1e-3) and cap["side"] == "adverse"
    assert "lands_short" in rules(reps["KAVERI"])
    s = ind(reps["SARANG"], "landing")  # credit cost: above the midpoint is adverse
    assert all(r["side"] == "adverse" for r in s["rows"] if r["metric"] == "Credit cost")


def test_revisions_direction_and_first_target(reps):
    h = ind(reps["HALCYON"], "revisions")
    assert h["repeated"] == [{"metric": "Revenue growth (constant currency)", "periods": ["FY25", "FY26", "FY27"]}]
    k = ind(reps["KAVERI"], "revisions")
    capex25 = next(r for r in k["rows"] if r["metric"] == "Capex" and r["period"] == "FY25")
    assert capex25["first_target_met"] is False and capex25["verdict"] == "delivered"
    assert k["met_only_after_revision"] == [capex25["ledger"]]
    s = ind(reps["SARANG"], "revisions")
    cc = next(r for r in s["rows"] if r["metric"] == "Credit cost")
    assert cc["adverse"] == 1 and cc["changes"][0]["change"] == "raised"  # raising a cost range is against the company
    assert ind(reps["VEDIKA"], "revisions")["n"] == 0  # the presentation/call mismatch is a contradiction, not a revision


def test_capex_execution_uses_first_stated_plan(reps):
    c = ind(reps["KAVERI"], "capex")
    got = {r["period"]: r["execution_value"] for r in c["rows"] if r["execution_value"] is not None}
    assert got == {"FY25": pytest.approx(951.6 / 1100, abs=1e-3), "FY26": pytest.approx(1020 / 1200, abs=1e-3)}
    assert "capex_below_plan" in rules(reps["KAVERI"])
    assert "capex_below_plan" not in rules(reps["HALCYON"])  # 99% and 98%


def test_quiet_then_missed(reps):
    sl = ind(reps["KAVERI"], "silence")
    rev = next(r for r in sl["rows"] if r["metric"] == "Revenue" and r["period"] == "FY26")
    assert rev["outcome"] == "missed" and sum(q["change"] == "not repeated" for q in rev["quiet"]) == 3
    assert all(r["metric"] != "Utilisation" for r in sl["rows"])  # not checkable, so not evidence of anything


def test_record_versus_current_year(reps):
    v = reps["VEDIKA"]
    assert "record_vs_current" in rules(v)
    assert "record_vs_current" not in rules(reps["HALCYON"])  # its open target is on track


def test_cash_against_profit(reps):
    k = ind(reps["KAVERI"], "cash")
    assert [r["period"] for r in k["rows"]] == ["FY24", "FY25", "FY26"]
    assert k["contradictions"] and k["management_said"]
    assert "cash_claim_vs_statement" in rules(reps["KAVERI"])
    h = ind(reps["HALCYON"], "cash")
    assert h["management_said"] and not h["contradictions"]  # "strong cash generation" at 84% of EBITDA is fair
    assert ind(reps["SARANG"], "cash")["status"] == "none"


def test_contradiction_detection(reps):
    v = {x["rule"]: x for x in reps["VEDIKA"]["credibility"]["contradictions"]}
    assert "24.5–25.5%" in v["documents_disagree"]["text"] and "24–25%" in v["documents_disagree"]["text"]
    debt = next(e for e in reps["VEDIKA"]["ledger"] if e["kind"] == "assertion" and e["metric"] == "net_debt")
    assert debt["verdict"] == "contradicted"  # "we continued to reduce debt" while net debt rose
    k = [x["text"] for x in reps["KAVERI"]["credibility"]["contradictions"]]
    assert any("cash generation" in t for t in k) and any("demand" in t for t in k)
    assert not reps["HALCYON"]["credibility"]["contradictions"]


def test_lanes_pair_statements_with_reported_path(reps):
    lanes = {l["label"]: l for l in reps["KAVERI"]["credibility"]["lanes"]}
    cap = lanes["Capex"]
    bands = [s for s in cap["statements"] if s["kind"] == "explicit"]
    assert bands and all(s["date"] <= (s["until"] or "9999") for s in bands)
    fy25 = [s for s in bands if s["period"] == "FY25"]
    assert [s["band"]["low"] for s in fy25] == [1045.0, 950.0]  # the revision is visible as a step
    assert {o["period"]: o["verdict"] for o in cap["outcomes"] if o["closed"]} == {"FY25": "delivered", "FY26": "missed"}
    marg = lanes["EBITDA margin"]
    assert len([a for a in marg["actuals"] if a["kind"] == "quarter"]) >= 12
    assert not lanes["Utilisation"]["checkable"] and lanes["Utilisation"]["reason"]


def test_every_credibility_item_resolves(reps):
    for r in reps.values():
        facts = r["facts"]
        for p in r["credibility"]["interpretation"]:
            assert p["evidence"] and all(e in facts for e in p["evidence"]) and p["method"] == "rules"
        for lane in r["credibility"]["lanes"]:
            assert all(a["fact"] in facts for a in lane["actuals"])
            assert all(s["fact"] in facts for s in lane["statements"] if s["fact"])
        assert r["audit"]["ok"]


def test_model_rewrite_is_rejected_when_it_adds_a_number():
    rewrite = model_rephraser(lambda prompt: '{"text": "Capex ran at 86% of plan, and will be 70% next year."}', "test-model")
    assert rewrite("Capex has come in at 86% of the first-stated plan.", "86% ₹951.6 cr") is None
    ok = model_rephraser(lambda prompt: '{"text": "Capex came in at 86% of the plan first stated."}', "test-model")
    assert ok("Capex has come in at 86% of the first-stated plan.", "86%") == "Capex came in at 86% of the plan first stated."
    # A rewrite that swaps in words the facts don't contain is not kept; FINN's own sentence stays.
    loose = model_rephraser(lambda prompt: '{"text": "Spending reached 86% of what was budgeted, a sign of discipline."}', "test-model")
    assert loose("Capex has come in at 86% of the first-stated plan.", "86%") is None


def test_company_without_documents(reps):
    c = reps["CORAL"]["credibility"]
    assert all(i["status"] == "none" for i in c["indicators"]) and c["interpretation"] == [] and c["lanes"] == []
