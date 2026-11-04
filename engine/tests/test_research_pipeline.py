"""Pull research end to end on synthetic companies from four sectors, plus error paths."""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

import pymupdf
import pytest

from finn_engine.models import FetchLog
from finn_engine.research import fixtures as RF
from finn_engine.research import periods as P
from finn_engine.research.pdftext import norm
from finn_engine.research.pipeline import ResearchError, run, write
from finn_engine.research.service import Inputs, Service, handler, search
from finn_engine.research.sources import SEED_MASTER, FileInputs, parse_master

SYMBOLS = ["HALCYON", "KAVERI", "SARANG", "VEDIKA", "CORAL"]


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("research")
    RF.build(root / "inputs")
    inp = FileInputs(root / "inputs")
    reports = {s: run(s, inp, as_of=RF.AS_OF) for s in SYMBOLS}
    return root, inp, reports


def entry(rep: dict, metric: str, period: str, kind: str = "guidance", segment: str | None = None) -> dict:
    hits = [e for e in rep["ledger"] if e["metric"] == metric and e.get("period") == period and e["kind"] == kind and e.get("segment") == segment]
    assert len(hits) == 1, [(e["metric"], e.get("period")) for e in rep["ledger"]]
    return hits[0]


# ------------------------------------------------------------------ labelling and coverage

def test_fixture_reports_are_labelled_and_have_no_exchange_urls(built):
    _, _, reps = built
    for r in reps.values():
        assert r["dataset"] == "fixture" and "SYNTHETIC" in r["dataset_note"]
        assert all(d["fixture"] and d["url"] is None and d["listing_url"] is None for d in r["documents"])
        assert r["identity"]["isin"].startswith("INFIXT")


def test_every_fixture_pdf_carries_the_synthetic_stamp(built):
    root, _, _ = built
    for p in (root / "inputs" / "attachments").glob("*.pdf"):
        doc = pymupdf.open(p)
        text = doc[0].get_text()
        assert "SYNTHETIC TEST DOCUMENT" in text or doc[0].get_images(), p.name


def test_document_selection(built):
    _, _, reps = built
    h = reps["HALCYON"]
    results = sorted(d["period"] for d in h["documents"] if d["kind"] == "results")
    assert results == sorted(RF.FILING_QS)  # latest ten quarters; the older Q4 FY24 filing is left out
    assert not any(d["period"] == RF.OLD_RESULTS for d in h["documents"])
    tr = next(d for d in h["documents"] if d["kind"] == "transcript" and d["period"] == "Q1 FY27")
    assert tr["status"] == "parsed" and "nse copy" in tr["parse"]["downloaded_from"]  # BSE attachment missing
    k = reps["KAVERI"]
    scanned = next(d for d in k["documents"] if d["kind"] == "presentation" and d["period"] == "Q3 FY26")
    assert scanned["status"] == "failed" and "scanned" in scanned["status_reason"]
    assert any("Kaveri Roadways" in x for x in k["rejections"])
    assert any("Q1 FY27 call transcript" in g["detail"] for g in reps["VEDIKA"]["gaps"])


def test_company_with_no_research_documents(built):
    _, _, reps = built
    c = reps["CORAL"]
    assert c["documents"] == [] and c["facts"] == {} and c["ledger"] == []
    assert {g["area"] for g in c["gaps"]} >= {"Numbers", "Narrative vs Numbers"}
    assert c["sections"]["snapshot"]["rows"] == []


# ------------------------------------------------------------------ numbers path

def test_reported_figures_match_the_documents(built):
    _, _, reps = built
    truth = RF.truth()
    checked = 0
    for sym in ("HALCYON", "KAVERI", "SARANG", "VEDIKA"):
        t = truth[sym]
        for fid, f in reps[sym]["facts"].items():
            if not fid.startswith("r:pl:"):
                continue
            _, _, per, key = fid.split(":", 3)
            label = re.sub(r"^(Q\d|H\d|9M)?FY", lambda m: (m.group(1) + " " if m.group(1) else "") + "FY", per)
            qs = P.quarters(label)
            if all(q in t["pl"] for q in qs) and key in t["pl"][qs[0]]:
                assert f["value"] == pytest.approx(sum(t["pl"][q][key] for q in qs), abs=0.02), fid
                checked += 1
    assert checked > 200


def test_consolidated_preferred_and_units_converted(built):
    _, _, reps = built
    k = reps["KAVERI"]  # lakhs, standalone page first
    assert k["sections"]["snapshot"]["basis"] == "consolidated"
    assert k["facts"]["r:pl:Q2FY27:revenue"]["value"] == 1655.0
    v = reps["VEDIKA"]  # million
    assert v["facts"]["r:pl:Q2FY27:revenue"]["value"] == 1820.0
    assert all(c["ok"] for c in k["checks"])


def test_lender_balance_sheet_and_credit_cost(built):
    _, _, reps = built
    s = reps["SARANG"]
    assert s["facts"]["r:bs:FY26:loans"]["value"] == 22600
    assert s["facts"]["r:bs:H1FY27:borrowings"]["value"] == 8300 + 11700 + 850
    cc = s["facts"]["c:FY26:credit_cost"]
    assert cc["value"] == pytest.approx(460 / ((18400 + 22600) / 2), abs=1e-4)
    assert "average" in cc["formula"] and len(cc["inputs"]) == 3
    assert s["sections"]["cash_quality"]["note"]  # lenders get no FCF / conversion


def test_computed_figures_carry_formula_and_inputs(built):
    _, _, reps = built
    for r in reps.values():
        for f in r["facts"].values():
            if f["info_class"] == "computed":
                assert f["formula"] and f["inputs"] and all(i in r["facts"] for i in f["inputs"])
        assert r["audit"]["ok"]


# ------------------------------------------------------------------ evidence

def test_quotes_and_rows_are_on_the_cited_page(built):
    """Independent re-read: every quote and every reported row appears on its page."""
    root, _, reps = built
    att = root / "inputs" / "attachments"
    for r in reps.values():
        docs = {d["id"]: d for d in r["documents"]}
        texts: dict[str, list[str]] = {}
        for f in r["facts"].values():
            if not f.get("doc_id"):
                continue
            d = docs[f["doc_id"]]
            name = d["parse"].get("downloaded_from") and next(a["attachment"] for a in d["parse"]["alternates"]) or d["parse"]["attachment"]
            if name not in texts:
                texts[name] = [re.sub(r"\s+", " ", norm(p.get_text())).lower() for p in pymupdf.open(att / name)]
            page = texts[name][f["page"] - 1]
            if f.get("quote"):
                assert norm(f["quote"]).lower()[:100] in page, (f["id"], f["page"], f["quote"][:60])
            if f.get("row_text"):
                letters = lambda x: re.sub(r"[^a-z]", "", x.lower())  # noqa: E731
                label = letters(f["row_text"].split(" | ")[0])[:30]
                assert label in letters(page), (f["id"], label)


def test_guidance_quotes_carry_speaker_section_and_page(built):
    _, _, reps = built
    for r in reps.values():
        for c in r["claims"]:
            if c["doc_kind"] == "transcript":
                assert c["speaker"] and c["section"] in ("Prepared remarks", "Q&A") and c["page"] >= 1
                assert c["role"] == "management"
    pages = {c["page"] for c in reps["HALCYON"]["claims"] if c["doc_kind"] == "transcript"}
    assert len(pages) > 1  # statements are found beyond the first page


def test_explicit_guidance_has_a_number_from_the_quote(built):
    _, _, reps = built
    for r in reps.values():
        for c in r["claims"]:
            if c["kind"] == "guidance" and c.get("target") and c["explicit"]:
                nums = set(re.findall(r"\d[\d,]*(?:\.\d+)?", c["target"]["text"]))
                if not nums:  # the literal number words: "double-digit", "doubling"
                    assert re.search(r"double|doubl|tripl", c["target"]["text"], re.I) and "literally" in c["target"]["reading"] or c["target"]["kind"] == "multiple"
                    continue
                assert all(n in c["quote"] or n.replace(",", "") in c["quote"].replace(",", "") for n in nums), c["quote"]


# ------------------------------------------------------------------ narrative vs numbers: planted cases

PLANTED = [
    ("HALCYON", "ebit_margin", "FY26", "delivered", None),
    ("HALCYON", "ebit_margin", "FY27", "pending", "on track"),
    ("HALCYON", "revenue_growth_cc", "FY27", "unverifiable", None),
    ("KAVERI", "capex", "FY26", "missed", None),
    ("KAVERI", "ebitda_margin", "FY27", "dropped", "not repeated; behind"),
    ("KAVERI", "net_debt", "FY27", "dropped", "not repeated; behind"),
    ("KAVERI", "revenue", "FY27", "unverifiable", "words only"),
    # H1 capex ₹610 cr is 41% of the ~₹1,500 cr plan at the half-year: behind a straight-line pace (review fix R-12).
    ("KAVERI", "capex", "FY27", "dropped", "not repeated; behind"),
    ("SARANG", "credit_cost", "FY26", "missed", None),
    ("SARANG", "credit_cost", "FY27", "dropped", "withdrawn; behind"),
    ("SARANG", "aum_growth", "FY27", "unverifiable", None),
    ("VEDIKA", "ebitda_margin", "FY26", "delivered", None),
    ("VEDIKA", "revenue", "FY27", "dropped", "not repeated; behind"),
    ("VEDIKA", "ebitda_margin", "FY27", "dropped", "not repeated; behind"),
]


@pytest.mark.parametrize("sym,metric,period,verdict,note", PLANTED)
def test_planted_guidance_verdicts(built, sym, metric, period, verdict, note):
    e = entry(built[2][sym], metric, period)
    assert e["verdict"] == verdict, e["detail"]
    assert e.get("status_note") == note, e["detail"]
    assert e["evidence"]


def test_guidance_history(built):
    _, _, reps = built
    h = entry(reps["HALCYON"], "ebit_margin", "FY27")
    assert [x["change"] for x in h["history"]] == ["first", "reiterated", "lowered", "also stated"]
    v = entry(reps["VEDIKA"], "revenue", "FY27")
    assert v["history"][-1]["change"] == "softened"  # the number was restated only as "healthy growth"


def test_words_only_guidance_shows_actual_but_no_verdict(built):
    e = entry(built[2]["KAVERI"], "revenue", "FY27")
    assert not e["explicit"] and e["target"].startswith("“") and e["actual_fact"]
    assert "doesn't score" in e["detail"]


def test_segment_guidance_uses_segment_revenue(built):
    e = next(x for x in built[2]["VEDIKA"]["ledger"] if x.get("segment"))
    assert e["segment"] == "US generics" and e["verdict"] == "dropped"
    act = built[2]["VEDIKA"]["facts"][e["actual_fact"]]
    assert act["value"] == pytest.approx((600 + 637) / (585 + 610) - 1, abs=1e-4)


def test_assertions_checked_on_their_basis(built):
    _, _, reps = built
    asrt = [e for e in reps["HALCYON"]["ledger"] if e["kind"] == "assertion" and e["metric"] == "revenue"]
    assert asrt and all(e["verdict"] == "consistent" for e in asrt)
    loan = entry(reps["SARANG"], "loan_growth", "Q2 FY27", "assertion")
    assert loan["verdict"] == "consistent"
    nim = entry(reps["SARANG"], "nim", "FY26", "assertion")
    assert nim["verdict"] == "unverifiable"  # different denominator; never compared


def test_discrepancies_and_shifts(built):
    _, _, reps = built
    rules = {s: {d["rule"] for d in r["sections"]["nvn"]["discrepancies"]} for s, r in reps.items()}
    assert "commentary_vs_numbers" in rules["KAVERI"]
    assert {"guidance_lowered"} <= rules["HALCYON"]
    assert {"guidance_missed", "guidance_dropped"} <= rules["SARANG"]
    shifts = {s: {(x["theme"], x["to_tone"]) for x in r["sections"]["nvn"]["shifts"]} for s, r in reps.items()}
    assert ("Client spending", "negative") in shifts["HALCYON"]
    assert ("Pricing", "negative") in shifts["KAVERI"]
    assert ("Asset quality", "negative") in shifts["SARANG"]
    assert ("Regulation", "negative") in shifts["VEDIKA"]
    for r in reps.values():
        for d in r["sections"]["nvn"]["discrepancies"]:
            assert d["evidence"] and d["implication"]


def test_bull_bear_points_cite_facts_whose_numbers_they_use(built):
    _, _, reps = built
    for r in reps.values():
        f = r["facts"]
        for side in ("bull", "bear"):
            for p in r["sections"]["bull_bear"][side]:
                cited = p["rule"] + " " + " ".join((f[e].get("display") or "").replace("0.", "") + " " + (f[e].get("display") or "") + " " + (f[e].get("formula") or "") for e in p["evidence"]) + " " + " ".join(
                    x.get("target") or "" for e in r["ledger"] for x in e.get("history", []))
                text = re.sub(r"\b(?:Q[1-4]|H[12]|9M)?\s?FY\d{2}\b", "", p["text"])
                for n in re.findall(r"\d[\d,]*\d(?:\.\d+)?|\d\.\d+", text):
                    if n.replace(",", "").isdigit() and int(n.replace(",", "")) < 10:
                        continue
                    assert n in cited or n.rstrip(",") in cited or "of" in text and re.search(rf"\b{re.escape(n)} of \d+ explicit", text), (p["text"], n)


# ------------------------------------------------------------------ errors and unseen tickers

class Blocked:
    """Live sources that are all unreachable, with the bundled seed equity list."""
    dataset = "live"

    def __init__(self):
        self.seed = parse_master(SEED_MASTER.read_text())

    def _fail(self, target):
        return FetchLog(source="test", target=target, url=None, ok=False, error="unreachable", fetched_at="2026-11-04T00:00:00Z")

    def equity_master(self):
        log = self._fail("NSE equity list, seed copy dated 5 Nov 2023 (NSE couldn't be reached)")
        return self.seed, log

    def nse_meta(self, s):
        return None, self._fail(s)

    def bse_scrips(self):
        return [], self._fail("scrip list")

    def announcements(self, *a):
        return [], [self._fail("bse")]

    def nse_announcements(self, *a):
        return [], [self._fail("nse")]

    def annual_reports(self, s):
        return [], self._fail("ar")

    def ir_documents(self, s):
        return []

    def download(self, ref):
        return None, self._fail(ref)


def test_real_ticker_with_sources_unreachable():
    with pytest.raises(ResearchError) as e:
        run("POLYCAB", Blocked())
    assert e.value.code == "SOURCES_UNAVAILABLE"
    idn = e.value.detail["identity"]
    assert idn["name"] == "Polycab India Limited" and idn["isin"] == "INE455K01017"
    assert any("November 2023" in n for n in idn["notes"])


def test_unknown_and_invalid_symbols(built):
    _, inp, _ = built
    with pytest.raises(ResearchError) as e:
        run("NOSUCHCO", inp)
    assert e.value.code == "UNKNOWN_SYMBOL"
    with pytest.raises(ResearchError) as e:
        run("NOSUCHCO", Blocked())
    assert e.value.code == "UNVERIFIED_SYMBOL"  # only the 2023 copy was checked
    with pytest.raises(ResearchError) as e:
        run("bad symbol!", inp)
    assert e.value.code == "INVALID_SYMBOL"
    assert run("kaveri.ns", inp, as_of=RF.AS_OF)["identity"]["symbol"] == "KAVERI"


def test_reports_are_deterministic(built):
    _, inp, reps = built
    again = run("KAVERI", inp, as_of=RF.AS_OF)
    def strip(r: dict) -> dict:
        out = {k: v for k, v in r.items() if k not in ("generated_at", "fetch_log")}
        out["documents"] = [{k: v for k, v in d.items() if k != "fetched_at"} for d in r["documents"]]  # download time
        return out
    assert json.dumps(strip(again), sort_keys=True, default=str) == json.dumps(strip(reps["KAVERI"]), sort_keys=True, default=str)


# ------------------------------------------------------------------ service

def test_search_ranks_exact_then_prefix():
    rows = [{"symbol": "TITAN", "name": "Titan Company"}, {"symbol": "TITANBIO", "name": "Titan Biotech"}, {"symbol": "XTITAN", "name": "X"}]
    assert [r["symbol"] for r in search(rows, "titan")] == ["TITAN", "TITANBIO", "XTITAN"]


def test_service_runs_jobs_and_serves_reports(built, tmp_path):
    root, inp, _ = built
    svc = Service(Inputs(None, inp), tmp_path, as_of=RF.AS_OF)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(svc))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        sec = json.load(urllib.request.urlopen(f"{base}/v1/securities?q=sar"))["results"]
        assert sec[0]["symbol"] == "SARANG" and sec[0]["fixture"]
        req = urllib.request.Request(f"{base}/v1/research/SARANG", method="POST")
        assert json.load(urllib.request.urlopen(req))["symbol"] == "SARANG"
        for _ in range(100):
            job = json.load(urllib.request.urlopen(f"{base}/v1/research/SARANG/job"))
            if job["status"] in ("done", "error"):
                break
            threading.Event().wait(0.05)
        assert job["status"] == "done", job
        rep = json.load(urllib.request.urlopen(f"{base}/v1/research/SARANG"))
        assert rep["identity"]["symbol"] == "SARANG"
        idx = json.load(urllib.request.urlopen(f"{base}/v1/research"))
        assert [c["symbol"] for c in idx["companies"]] == ["SARANG"]
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/v1/research/VEDIKA")
        assert e.value.code == 404
    finally:
        srv.shutdown()


def test_write_keeps_an_index(built, tmp_path):
    _, _, reps = built
    write(reps["KAVERI"], tmp_path)
    write(reps["SARANG"], tmp_path)
    idx = json.loads((tmp_path / "index.json").read_text())
    assert [c["symbol"] for c in idx["companies"]] == ["KAVERI", "SARANG"]
    assert all(c["dataset"] == "fixture" for c in idx["companies"])
