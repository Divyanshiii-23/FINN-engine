"""Regression tests for the issues found in the code review (REVIEW.md).

Each test names the finding it guards.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from finn_engine.research import fixtures as RF
from finn_engine.research import pipeline as RP
from finn_engine.research.ask import answer, validate
from finn_engine.research.service import Inputs, Service, handler
from finn_engine.research.sources import FileInputs, LiveInputs
from finn_engine.sources.http import HttpClient, host_allowed


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("review")
    RF.build(root / "inputs")
    inp = FileInputs(root / "inputs")
    out = root / "out"
    out.mkdir()
    for s in ("HALCYON", "KAVERI"):
        RP.write(RP.run(s, inp, as_of=RF.AS_OF), out)
    return root, inp, out


# ---------------------------------------------------------------- R-01 SSRF / local file read

def test_exchange_hosts_only():
    assert host_allowed("https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf")
    assert host_allowed("https://nsearchives.nseindia.com/corporate/x.pdf")
    for bad in ("http://www.bseindia.com/x.pdf", "https://169.254.169.254/latest/meta-data", "https://bseindia.com.evil.example/x.pdf",
                "file:///etc/passwd", "https://localhost:8787/v1/research"):
        assert not host_allowed(bad), bad


class _NoNet(HttpClient):
    def __init__(self):
        super().__init__(Path("/tmp/finn-test-raw"))
        self.asked: list[str] = []

    def _fetch(self, url, params, headers, stream, hosts):  # never touches the network
        self.asked.append(url)
        raise AssertionError("network must not be reached")


def test_untrusted_refs_cannot_read_files_or_reach_other_hosts(tmp_path):
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"%PDF-1.4 secret")
    c = _NoNet()
    live = LiveInputs(c, tmp_path)
    for ref in (str(secret), f"file://{secret}", "https://169.254.169.254/latest/meta-data/iam"):
        body, log = live.download(ref)
        assert body is None and not log.ok, ref
    assert c.asked == []
    # A document the operator supplies on the command line is still read.
    body, log = live.download(str(secret), trusted=True)
    assert body == b"%PDF-1.4 secret" and log.ok


def test_fixture_refs_stay_inside_the_fixture_directory(world, tmp_path):
    _, inp, _ = world
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF outside")
    body, _ = inp.download(str(outside))
    assert body is None


# ---------------------------------------------------------------- R-03 engine HTTP surface

@pytest.fixture()
def server(world, monkeypatch):
    _, inp, out = world
    svc = Service(Inputs(None, inp), out)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(svc))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield svc, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, body: bytes, headers=None):
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_body_limit_and_bad_json(server):
    _, base = server
    code, body = _post(f"{base}/v1/ask/HALCYON", b'{"question": "' + b"x" * 5000 + b'"}')
    assert code == 413 and body["error"] == "BODY_TOO_LARGE"
    code, body = _post(f"{base}/v1/ask/HALCYON", b"not json")
    assert code == 400 and body["error"] == "BAD_JSON"


def test_token_required_when_configured(server, monkeypatch):
    _, base = server
    monkeypatch.setenv("FINN_ENGINE_TOKEN", "s3cret")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"{base}/v1/research")
    assert e.value.code == 401
    ok = urllib.request.urlopen(urllib.request.Request(f"{base}/v1/research", headers={"Authorization": "Bearer s3cret"}))
    assert ok.status == 200
    assert urllib.request.urlopen(f"{base}/health").status == 200  # liveness stays open


def test_concurrent_jobs_are_capped(server):
    svc, base = server
    gate = threading.Event()
    svc._run = lambda j: gate.wait(5)  # hold jobs open
    try:
        assert _post(f"{base}/v1/research/HALCYON", b"")[0] == 202
        assert _post(f"{base}/v1/research/KAVERI", b"")[0] == 202
        code, body = _post(f"{base}/v1/research/SARANG", b"")
        assert code == 429 and body["error"] == "BUSY"
    finally:
        gate.set()


def test_internal_errors_do_not_leak_a_traceback(world, tmp_path):
    _, inp, _ = world
    svc = Service(Inputs(None, inp), tmp_path)

    def boom(*a, **k):
        raise RuntimeError("/srv/secret/path exploded")
    orig, RP.run = RP.run, boom
    try:
        j = svc.start("HALCYON")
        for _ in range(50):
            if j.status == "error":
                break
            threading.Event().wait(0.05)
    finally:
        RP.run = orig
    assert j.error["code"] == "INTERNAL" and "trace" not in j.error and "/srv/secret" not in json.dumps(j.error)


def test_fixture_service_pins_the_fixture_date(world, tmp_path):
    _, inp, _ = world
    assert Service(Inputs(None, inp), tmp_path).as_of == RF.AS_OF


def test_reports_are_cached_until_the_file_changes(server, world):
    svc, _ = server
    a = svc.report("HALCYON")
    assert svc.report("HALCYON") is a  # no re-read
    svc.ask("HALCYON", "Why did margins decline?")
    ak = svc._askers["HALCYON"][1]
    svc.ask("HALCYON", "Is operating cash flow supporting profits?")
    assert svc._askers["HALCYON"][1] is ak  # BM25 index reused


# ---------------------------------------------------------------- R-05/R-06 Ask hallucination pathways

def _rep(world, sym="HALCYON"):
    out = world[2]
    return json.loads((out / f"{sym}.json").read_text()), json.loads((out / f"{sym}.passages.json").read_text())


def test_named_year_is_not_silently_swapped_for_the_latest_quarter(world):
    rep, ps = _rep(world)
    a = answer("Why did margins decline in FY26?", rep, ps)
    assert a["blocks"][0]["kind"] == "note" and "FY26" in a["blocks"][0]["text"] and "Q4 FY26" in a["blocks"][0]["text"]
    assert any("For FY26 as a whole" in b["text"] for b in a["blocks"])
    assert not any("Q2 FY27" in b["text"] for b in a["blocks"] if b["kind"] == "fact")
    gone = answer("Why did margins decline in FY22?", rep, ps)
    assert gone["status"] == "insufficient" and "FY22" in gone["blocks"][0]["text"]


@pytest.mark.parametrize("q,scope", [("What did management predict for capex?", False), ("What did the auditor recommend?", False),
                                     ("Should I recommend this stock to clients?", True), ("Would you recommend buying it?", True),
                                     ("Can you predict the share price?", True), ("Is it undervalued?", True)])
def test_out_of_scope_is_about_advice_not_vocabulary(world, q, scope):
    rep, ps = _rep(world)
    assert (answer(q, rep, ps)["status"] == "out_of_scope") is scope


def test_question_text_is_not_evidence(world):
    rep, ps = _rep(world)
    fid = next(k for k in rep["facts"] if k.endswith(":ebit_margin"))
    block = {"kind": "fact", "text": "EBIT margin will reach 31.5% next year.", "cites": [fid]}
    assert validate(block, rep, {}, "Will EBIT margin reach 31.5%?", strict=True)


def test_strict_validation_rejects_an_added_cause(world):
    rep, ps = _rep(world)
    fid = next(k for k in rep["facts"] if k.endswith(":ebit_margin"))
    f = rep["facts"][fid]
    block = {"kind": "fact", "text": f"EBIT margin was {f['display']} due to pricing pressure.", "cites": [fid]}
    assert "cause" in (validate(block, rep, {}, "", strict=True) or "")


# ---------------------------------------------------------------- R-10/R-11 data plumbing

def test_index_survives_concurrent_writes(world, tmp_path):
    _, inp, out = world
    reps = [json.loads((out / f"{s}.json").read_text()) for s in ("HALCYON", "KAVERI")]
    ps = {s: json.loads((out / f"{s}.passages.json").read_text()) for s in ("HALCYON", "KAVERI")}
    for r in reps:
        r["passages"] = ps[r["identity"]["symbol"]]
    errors: list[BaseException] = []

    def go(r):
        try:
            RP.write(json.loads(json.dumps(r)), tmp_path)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=go, args=(r,)) for r in reps for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors, errors
    assert json.loads((tmp_path / "HALCYON.json").read_text())["identity"]["symbol"] == "HALCYON"
    idx = json.loads((tmp_path / "index.json").read_text())
    assert sorted(c["symbol"] for c in idx["companies"]) == ["HALCYON", "KAVERI"]


def test_bse_scrip_list_falls_back_to_an_older_copy(tmp_path):
    class Down(HttpClient):
        def __init__(self):
            super().__init__(tmp_path / "raw", retries=0)

        def get(self, *a, **k):
            from finn_engine.models import FetchLog
            return None, FetchLog(source="bse", target="scrip list", url="x", ok=False, error="HTTP 503", fetched_at=datetime.now())
    stale = tmp_path / "bse_scrips.json"
    stale.write_text(json.dumps([{"SCRIP_CD": "500180", "ISIN_NUMBER": "INE040A01034", "INDUSTRY": "Private Sector Bank"}]))
    old = (datetime.now() - timedelta(days=3)).timestamp()
    import os
    os.utime(stale, (old, old))
    rows, log = LiveInputs(Down(), tmp_path).bse_scrips()
    assert rows and log.ok and "cached copy from" in log.target and "HTTP 503" in log.target


def test_lender_is_detected_from_the_name_when_industry_is_unknown():
    assert RP.FIN_NAME.search("HDFC Bank Limited") and RP.FIN_NAME.search("Bajaj Finance Limited")
    assert not RP.FIN_NAME.search("Bankim Textiles") and not RP.FIN_NAME.search("Polycab India Limited")


def test_bse_pagination_cap_is_reported():
    from finn_engine.models import Company, FetchLog
    from finn_engine.sources import bse

    class Pages:
        def get(self, source, target, url, params=None, headers=None, **k):
            return {"Table": [{"NEWSID": f"{params['pageno']}-{i}"} for i in range(50)], "Table1": [{"ROWCNT": 2000}]}, FetchLog(
                source="bse", target=target, url=url, ok=True, fetched_at=datetime.now())
    rows, logs = bse.fetch(Pages(), Company(symbol="X", name="X", bse_code="500001"), date(2024, 1, 1), date(2026, 11, 1), max_pages=3)
    assert len(rows) == 150 and not logs[-1].ok and "150 of 2000" in logs[-1].error
