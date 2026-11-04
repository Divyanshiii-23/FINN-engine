"""On-demand Pull research: ticker search, background jobs, and a small HTTP API.

Reports are written as JSON files (one per symbol) plus an index; the web app
reads them through the API. A research job for a symbol runs once at a time;
asking again while it runs returns the running job.

    GET  /health
    GET  /v1/securities?q=TEXT           ticker search over NSE's equity list
    GET  /v1/research                    index of built reports
    GET  /v1/research/SYMBOL             the latest report (404 if none)
    POST /v1/research/SYMBOL             start (or join) a research job → 202
    GET  /v1/research/SYMBOL/job         job status: queued | running | done | error
    POST /v1/ask/SYMBOL {"question"}     Ask FINN: an answer grounded in that company's documents
    GET  /v1/research/SYMBOL/doc/DOC_ID  a document's passages by page, for source navigation

No framework: the standard library's threaded HTTP server is enough for one
analyst's on-demand use, and keeps the deployment to one process.
"""

from __future__ import annotations

import json
import re
import threading
import traceback
import hmac
import sys
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ..sources.http import HttpClient
from . import pipeline as RP
from .sources import SEED_MASTER, FileInputs, LiveInputs, parse_master


class Inputs:
    """Fixture companies from a fixture directory; everything else from live sources."""

    def __init__(self, live: LiveInputs | None, fixtures: FileInputs | None):
        self.live, self.fixtures = live, fixtures
        self._fixture_syms = {r["SYMBOL"].upper() for r in (fixtures.equity_master()[0] if fixtures else [])}

    def for_symbol(self, symbol: str):
        if self.fixtures and symbol in self._fixture_syms:
            return self.fixtures
        if self.live:
            return self.live
        if self.fixtures:
            return self.fixtures
        raise RP.ResearchError("NO_SOURCES", "No inputs configured.")

    def securities(self) -> list[dict]:
        rows: list[dict] = []
        if self.fixtures:
            for r in self.fixtures.equity_master()[0]:
                rows.append({"symbol": r["SYMBOL"], "name": r.get("NAME OF COMPANY", ""), "isin": r.get("ISIN NUMBER", ""), "series": r.get("SERIES", ""), "fixture": True})
        if self.live:
            cached = self.live.cache / "EQUITY_L.csv"
            src, label = (cached, "NSE equity list (cached)") if cached.exists() else (SEED_MASTER, "NSE equity list, seed copy dated 5 Nov 2023")
            have = {r["symbol"] for r in rows}
            for r in parse_master(src.read_text()):
                if r.get("SYMBOL") and r["SYMBOL"] not in have:
                    rows.append({"symbol": r["SYMBOL"], "name": r.get("NAME OF COMPANY", ""), "isin": r.get("ISIN NUMBER", ""), "series": r.get("SERIES", ""), "fixture": False, "list": label})
        return rows


def _clean_query(q: str) -> str:
    """Accept the forms people paste: 'NSE:INFY', 'TCS.NS', 'RELIANCE.BO', 'BSE: TCS'."""
    q = q.strip().upper()
    q = re.sub(r"^(NSE|BSE)\s*:\s*", "", q)
    return re.sub(r"\.(NS|BO)$", "", q).strip()


def search(rows: list[dict], q: str, limit: int = 12) -> list[dict]:
    q = _clean_query(q)
    if not q:
        return []
    def rank(r: dict) -> tuple:
        s, n = r["symbol"].upper(), r["name"].upper()
        return (0 if s == q else 1 if s.startswith(q) else 2 if n.startswith(q) else 3 if q in s else 4, len(s), s)
    hits = [r for r in rows if q in r["symbol"].upper() or q in r["name"].upper()]
    return sorted(hits, key=rank)[:limit]


@dataclass
class Job:
    symbol: str
    status: str = "queued"  # queued | running | done | error
    stage: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    error: dict | None = None

    def view(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class Service:
    STAGES = ["resolve", "discover", "download", "numbers", "narrative", "ledger", "sections"]

    MAX_RUNNING = 2      # live research crawls the exchanges; keep it polite and bounded
    MAX_JOBS = 200       # finished jobs kept for status lookups

    def __init__(self, inputs: Inputs, out_dir: Path, as_of: date | None = None):
        self.inputs, self.out = inputs, out_dir
        # Fixture documents are dated around the fixture's own "today"; using the wall clock would
        # slide the window and the open/closed status of guidance as real days pass.
        if as_of is None and getattr(getattr(inputs, "fixtures", None), "fixture", False):
            from .fixtures import AS_OF
            as_of = AS_OF
        self.as_of = as_of
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self._cache: dict[Path, tuple[int, object]] = {}
        self._askers: dict[str, tuple[tuple[int, int], object]] = {}
        self._sec: list[dict] | None = None
        self.completer: tuple | None = None  # optional (complete, model) for Ask FINN

    def securities(self, q: str) -> list[dict]:
        if self._sec is None:
            self._sec = self.inputs.securities()
        return search(self._sec, q)

    def start(self, symbol: str) -> Job:
        sym = RP.normalise(symbol)
        with self.lock:
            j = self.jobs.get(sym)
            if j and j.status in ("queued", "running"):
                return j
            if sum(1 for x in self.jobs.values() if x.status in ("queued", "running")) >= self.MAX_RUNNING:
                raise Busy()
            if len(self.jobs) >= self.MAX_JOBS:
                for k in [k for k, x in self.jobs.items() if x.status not in ("queued", "running")][: len(self.jobs) - self.MAX_JOBS + 1]:
                    del self.jobs[k]
            j = Job(sym)
            self.jobs[sym] = j
        threading.Thread(target=self._run, args=(j,), daemon=True).start()
        return j

    def _run(self, j: Job) -> None:
        j.status = "running"
        try:
            inp = self.inputs.for_symbol(j.symbol)
            as_of = self.as_of if getattr(inp, "fixture", False) else None
            rep = RP.run(j.symbol, inp, as_of=as_of, progress=lambda s: setattr(j, "stage", s))
            RP.write(rep, self.out)
            j.status = "done"
        except RP.ResearchError as e:
            j.status, j.error = "error", {"code": e.code, "message": str(e), **e.detail}
        except Exception:  # noqa: BLE001
            # The trace goes to the server log only; clients get a stable code.
            print(f"research job {j.symbol} failed:\n{traceback.format_exc()}", file=sys.stderr)
            j.status, j.error = "error", {"code": "INTERNAL", "message": "The research run failed on the server. The error has been logged."}
        j.finished_at = datetime.now(timezone.utc).isoformat()

    def _load(self, p: Path, default):
        """Parsed JSON, re-read only when the file changes (reports are rewritten atomically)."""
        try:
            m = p.stat().st_mtime_ns
        except FileNotFoundError:
            return default
        hit = self._cache.get(p)
        if hit and hit[0] == m:
            return hit[1]
        v = json.loads(p.read_text())
        self._cache[p] = (m, v)
        return v

    def report(self, symbol: str) -> dict | None:
        return self._load(self.out / f"{RP.normalise(symbol)}.json", None)

    def passages(self, symbol: str) -> list[dict]:
        return self._load(self.out / f"{RP.normalise(symbol)}.passages.json", [])

    def ask(self, symbol: str, question: str) -> dict | None:
        from .ask import Asker, answer
        sym = RP.normalise(symbol)
        rep = self.report(sym)
        if rep is None:
            return None
        ps = self.passages(sym)
        key = tuple((self._cache.get(self.out / f) or (0,))[0] for f in (f"{sym}.json", f"{sym}.passages.json"))
        hit = self._askers.get(sym)
        if not hit or hit[0] != key:
            hit = (key, Asker(rep, ps))  # BM25 index built once per report version
            self._askers[sym] = hit
        return answer(question, rep, ps, *(self.completer or (None, "")), asker=hit[1])

    def document(self, symbol: str, doc_id: str) -> dict | None:
        rep = self.report(symbol)
        if rep is None:
            return None
        doc = next((d for d in rep["documents"] if d["id"] == doc_id), None)
        if doc is None:
            return None
        return {"document": doc, "passages": sorted([p for p in self.passages(symbol) if p["doc_id"] == doc_id], key=lambda p: (p["page"], p["id"]))}

    def index(self) -> dict:
        return self._load(self.out / "index.json", {"companies": []})


class Busy(Exception):
    pass


MAX_BODY = 4096


def handler(svc: Service):
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            raw = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt, *args):  # quieter logs
            return

        def _route(self, method: str) -> None:
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.split("/") if p]
            try:
                if parts == ["health"]:
                    return self._send(200, {"ok": True})
                tok = os.environ.get("FINN_ENGINE_TOKEN")
                if tok and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {tok}"):
                    return self._send(401, {"error": "UNAUTHORIZED", "message": "This engine needs a token."})
                if parts == ["v1", "securities"] and method == "GET":
                    q = parse_qs(u.query).get("q", [""])[0]
                    return self._send(200, {"results": svc.securities(q)})
                if parts == ["v1", "research"] and method == "GET":
                    return self._send(200, svc.index())
                if len(parts) == 3 and parts[:2] == ["v1", "research"]:
                    if method == "POST":
                        return self._send(202, svc.start(parts[2]).view())
                    rep = svc.report(parts[2])
                    job = svc.jobs.get(RP.normalise(parts[2]))
                    if rep is None:
                        return self._send(404, {"error": "NO_REPORT", "message": f"No report for {parts[2].upper()} yet.", "job": job.view() if job else None})
                    return self._send(200, rep)
                if len(parts) == 3 and parts[:2] == ["v1", "ask"] and method == "POST":
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                    except ValueError:
                        n = -1
                    if n < 0 or n > MAX_BODY:
                        return self._send(413, {"error": "BODY_TOO_LARGE", "message": f"Send at most {MAX_BODY} bytes."})
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                    except (ValueError, UnicodeDecodeError):
                        return self._send(400, {"error": "BAD_JSON", "message": "The body must be JSON: {\"question\": \"...\"}."})
                    if not isinstance(body, dict):
                        return self._send(400, {"error": "BAD_JSON", "message": "The body must be a JSON object."})
                    q = str(body.get("question") or "")
                    if not q.strip():
                        return self._send(400, {"error": "EMPTY_QUESTION", "message": "Ask a question about the company."})
                    ans = svc.ask(parts[2], q)
                    return self._send(200, ans) if ans else self._send(404, {"error": "NO_REPORT", "message": f"Research {parts[2].upper()} first; Ask FINN answers from its documents."})
                if len(parts) == 5 and parts[:2] == ["v1", "research"] and parts[3] == "doc":
                    d = svc.document(parts[2], parts[4])
                    return self._send(200, d) if d else self._send(404, {"error": "NO_DOCUMENT"})
                if len(parts) == 4 and parts[:2] == ["v1", "research"] and parts[3] == "job":
                    job = svc.jobs.get(RP.normalise(parts[2]))
                    return self._send(200 if job else 404, job.view() if job else {"error": "NO_JOB"})
                return self._send(404, {"error": "NOT_FOUND"})
            except RP.ResearchError as e:
                return self._send(400, {"error": e.code, "message": str(e)})
            except Busy:
                return self._send(429, {"error": "BUSY", "message": f"{Service.MAX_RUNNING} research runs are already in progress; try again shortly."})
            except Exception:  # noqa: BLE001
                print(f"request {method} {u.path} failed:\n{traceback.format_exc()}", file=sys.stderr)
                return self._send(500, {"error": "INTERNAL", "message": "The engine hit an error; it has been logged."})

        def do_GET(self):  # noqa: N802
            self._route("GET")

        def do_POST(self):  # noqa: N802
            self._route("POST")
    return H


def serve(svc: Service, host: str, port: int) -> None:
    srv = ThreadingHTTPServer((host, port), handler(svc))
    print(f"FINN research service on http://{host}:{port}  (reports in {svc.out})")
    srv.serve_forever()


def make_inputs(fixtures_dir: Path | None, live: bool, raw_dir: Path, cache_dir: Path) -> Inputs:
    fx = FileInputs(fixtures_dir) if fixtures_dir and fixtures_dir.exists() else None
    lv = LiveInputs(HttpClient(raw_dir), cache_dir) if live else None
    return Inputs(lv, fx)
