"""Command line.

  finn fixtures                      build synthetic fixtures and a fixture feed
  finn run --from D --to D           live run against BSE (+ --nse) and Yahoo
  finn run --inputs DIR --dataset live   run on real files you exported yourself
  finn digest --hours 24             print a windowed digest from a feed
  finn alerts --price 5 --volume 2   print alerts for given thresholds

  finn research SYMBOL               Pull research for any NSE ticker (live sources)
  finn research SYMBOL --inputs DIR  ... from saved exchange payloads instead
  finn research-fixtures             build the synthetic research fixtures and their reports
  finn serve                         on-demand research API for the web app (and Ask FINN)
  finn ask SYMBOL "question"         ask a question of a built report
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import fixtures as fx
from .config import DATA_DIR, ENGINE_DIR, load
from .export import build_feed, write
from .pipeline import FileInputs, LiveInputs, run
from .sources.http import HttpClient
from .store import Store

WEB_FEED = ENGINE_DIR.parent / "apps" / "web" / "data" / "feed.json"
WEB_RESEARCH = ENGINE_DIR.parent / "apps" / "web" / "data" / "research"
RESEARCH_FIXTURES = DATA_DIR / "research_fixtures"


def _research_summary(rep: dict, path: Path) -> None:
    c = rep["counts"]
    print(f"{rep['identity']['symbol']}  {rep['identity']['name']}  [{rep['dataset']}]")
    print(f"  documents {c['documents']}")
    print(f"  claims {c['claims']} (rejected by gates {c['claims_rejected_by_gates']}); verdicts {c['verdicts']}")
    for d in rep["sections"]["nvn"]["discrepancies"][:8]:
        print(f"  ! sev{d['severity']} {d['text'][:150]}")
    for g in rep["gaps"]:
        print(f"  gap: {g['detail']}")
    failed = [l for l in rep["fetch_log"] if not l["ok"]]
    if failed:
        print(f"  fetches failed: {len(failed)} of {len(rep['fetch_log'])}")
    print(f"  report written to {path}")


def cmd_research(a) -> int:
    from .research import pipeline as RP
    from .research.sources import FileInputs as RFiles
    from .research.sources import LiveInputs as RLive
    inp = RFiles(Path(a.inputs)) if a.inputs else RLive(HttpClient(DATA_DIR / "raw"), DATA_DIR / "cache")
    rephrase = None
    if a.llm:
        from .explain import gemini_completer
        from .research.credibility import model_rephraser
        g = gemini_completer()
        if g:
            rephrase = model_rephraser(*g)
        else:
            print("  --llm: GEMINI_API_KEY and FINN_EXPLAIN_MODEL aren't both set; interpretation stays rule-written.", file=sys.stderr)
    try:
        rep = RP.run(a.symbol, inp, as_of=date.fromisoformat(a.as_of) if a.as_of else None, progress=lambda s: print(f"  … {s}", file=sys.stderr), rephrase=rephrase)
    except RP.ResearchError as e:
        print(f"{e.code}: {e}")
        for l in e.detail.get("fetch_log", []):
            if not l["ok"]:
                print(f"  ! {l['source']} {l['target']}: {(l.get('error') or '')[:140]}")
        return 3
    _research_summary(rep, RP.write(rep, Path(a.out)))
    return 0


def cmd_research_fixtures(a) -> int:
    from .research import fixtures as RF
    from .research import pipeline as RP
    from .research.service import make_inputs
    import shutil
    out = Path(a.fixtures)
    shutil.rmtree(out, ignore_errors=True)
    RF.build(out)
    inp = make_inputs(out, False, DATA_DIR / "raw", DATA_DIR / "cache").fixtures
    assert inp
    for sym in [r["SYMBOL"] for r in inp.equity_master()[0]]:
        rep = RP.run(sym, inp, as_of=RF.AS_OF)
        _research_summary(rep, RP.write(rep, Path(a.out)))
    write_securities(out, Path(a.out))
    return 0


def write_securities(fixtures: Path | None, out: Path) -> None:
    """Static ticker list for the web app when no research service is running."""
    from .research.service import make_inputs
    rows = make_inputs(fixtures, True, DATA_DIR / "raw", DATA_DIR / "cache").securities()
    out.mkdir(parents=True, exist_ok=True)
    (out / "securities.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows}, separators=(",", ":")))
    print(f"securities list ({len(rows)} rows) written to {out / 'securities.json'}")


def cmd_ask(a) -> int:
    from .research.ask import answer
    rp, pp = Path(a.out) / f"{a.symbol.upper()}.json", Path(a.out) / f"{a.symbol.upper()}.passages.json"
    if not rp.exists():
        print(f"No report for {a.symbol.upper()}; run `finn research {a.symbol.upper()}` first.")
        return 3
    ans = answer(a.question, json.loads(rp.read_text()), json.loads(pp.read_text()) if pp.exists() else [])
    if a.json:
        print(json.dumps(ans, indent=1, default=str))
        return 0
    print(f"[{ans['status']}] {ans['intent']} {ans.get('topics')}")
    for b in ans["blocks"]:
        print(f"- {b['kind']}: {b['text']}  {b['cites'][:4]}")
        for c in b["cites"]:
            p = ans["passages"].get(c)
            if p:
                print(f"    \u201c{p['text'][:150]}\u201d ({p['doc_kind']} {p.get('period')}, p.{p['page']}{', ' + p['speaker'] if p.get('speaker') else ''})")
    return 0


def cmd_serve(a) -> int:
    from .research.service import Service, make_inputs, serve
    inp = make_inputs(Path(a.fixtures) if a.fixtures else None, not a.no_live, DATA_DIR / "raw", DATA_DIR / "cache")
    svc = Service(inp, Path(a.out))
    if a.llm:
        from .explain import gemini_completer
        svc.completer = gemini_completer()
        print("Ask FINN: " + (f"model {svc.completer[1]} writes answers, checked against citations" if svc.completer else "no model configured; answers are rule-written"))
    serve(svc, a.host, a.port)
    return 0


def _summary(res, feed_path: Path) -> None:
    tiers: dict[str, int] = {}
    for e in res.events:
        tiers[e.materiality.tier] = tiers.get(e.materiality.tier, 0) + 1
    failed = [l for l in res.logs if not l.ok]
    print(f"announcements {len(res.announcements)} (duplicates {sum(1 for a in res.announcements if a.duplicate_of)}), events {len(res.events)} {tiers}")
    print(f"fetches {len(res.logs)}, failed {len(failed)}; rejected rows {len(res.rejections)}")
    for l in failed[:12]:
        print(f"  ! {l.source} {l.target}: {l.error}")
    print(f"feed written to {feed_path}")


def cmd_fixtures(a) -> int:
    out = Path(a.out)
    fx.build(ENGINE_DIR, out)
    cfg = load(ENGINE_DIR / "fixtures" / "universe.yaml")
    store = Store(Path(a.db))
    res = run(cfg, FileInputs(out, fixture=True), store, fx.FIXTURE_FROM, fx.FIXTURE_TO, "fixture", use_llm=False)
    feed = build_feed(cfg, store, res, "fixture", as_of=fx.as_of())
    write(feed, Path(a.feed))
    _summary(res, Path(a.feed))
    return 0


def cmd_run(a) -> int:
    cfg = load(Path(a.config))
    end = date.fromisoformat(a.to) if a.to else date.today()
    start = date.fromisoformat(a.from_) if a.from_ else end - timedelta(days=7)
    store = Store(Path(a.db))
    if a.inputs:
        inputs = FileInputs(Path(a.inputs), fixture=a.dataset == "fixture")
    else:
        inputs = LiveInputs(HttpClient(DATA_DIR / "raw"), use_nse=a.nse)
    res = run(cfg, inputs, store, start, end, a.dataset, use_llm=not a.no_llm)
    feed = build_feed(cfg, store, res, a.dataset)
    write(feed, Path(a.feed))
    _summary(res, Path(a.feed))
    return 0 if res.events or not all(not l.ok for l in res.logs) else 2


def _load_feed(path: str) -> dict:
    return json.loads(Path(path).read_text())


def cmd_digest(a) -> int:
    feed = _load_feed(a.feed)
    now = datetime.fromisoformat(feed["as_of"])
    since = now - timedelta(hours=a.hours)
    evs = [e for e in feed["events"] if datetime.fromisoformat(e["last_filed_at"]) > since]
    print(f"{feed['dataset'].upper()} feed. {feed['dataset_note']}")
    print(f"Window: {since.isoformat()} to {now.isoformat()}  ({sum(len(e['announcements']) for e in evs)} filings, {len(evs)} events)\n")
    for tier in ("interrupt", "brief"):
        items = sorted([e for e in evs if e["materiality"]["tier"] == tier], key=lambda e: -e["materiality"]["score"])
        print(f"{'NEEDS YOU' if tier == 'interrupt' else 'WORTH A LOOK'} ({len(items)})")
        for e in items:
            print(f"  [{e['materiality']['score']:>3}] {e['symbol']:<10} {e['explanation']['what']}")
            print(f"        why: {e['explanation']['why']}")
    routine = [e for e in evs if e["materiality"]["tier"] == "routine"]
    print(f"\nROUTINE, collapsed ({len(routine)})")
    return 0


def cmd_alerts(a) -> int:
    feed = _load_feed(a.feed)
    cats = set(a.categories.split(",")) if a.categories else None
    print(f"{feed['dataset'].upper()} feed, session {feed['eod_date']}")
    for m in feed["market"]:
        s = m["signal"]
        price = s["ret_1d"] is not None and abs(s["ret_1d"]) * 100 >= a.price and not s["split_or_bonus_on_date"]
        vol = s["vol_ratio_20d"] is not None and s["vol_ratio_20d"] >= a.volume
        if price or vol:
            why = "explained by " + ", ".join(m["explaining_event_ids"]) if m["explaining_event_ids"] else "NO FILING EXPLAINS THIS MOVE"
            print(f"  MARKET {m['symbol']:<10} ret {s['ret_1d'] * 100:+.1f}%  vol {s['vol_ratio_20d'] or 0:.1f}x  {why}")
    for e in feed["events"]:
        if e["materiality"]["tier"] == "interrupt" and (cats is None or e["category"] in cats):
            print(f"  FILING {e['symbol']:<10} {e['title']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fixtures", help="build synthetic fixtures and a fixture feed")
    f.add_argument("--out", default=str(DATA_DIR / "fixtures"))
    f.add_argument("--db", default=str(DATA_DIR / "fixture.db"))
    f.add_argument("--feed", default=str(WEB_FEED))
    f.set_defaults(fn=cmd_fixtures)
    r = sub.add_parser("run", help="run the pipeline")
    r.add_argument("--config", default=str(ENGINE_DIR / "portfolio.yaml"))
    r.add_argument("--from", dest="from_")
    r.add_argument("--to")
    r.add_argument("--inputs", help="read files from this directory instead of the network")
    r.add_argument("--dataset", choices=["live", "fixture"], default="live")
    r.add_argument("--nse", action="store_true", help="also fetch NSE announcements")
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--db", default=str(DATA_DIR / "live.db"))
    r.add_argument("--feed", default=str(WEB_FEED))
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("digest", help="print a windowed digest")
    d.add_argument("--feed", default=str(WEB_FEED))
    d.add_argument("--hours", type=float, default=24)
    d.set_defaults(fn=cmd_digest)
    al = sub.add_parser("alerts", help="print alerts for thresholds")
    al.add_argument("--feed", default=str(WEB_FEED))
    al.add_argument("--price", type=float, default=5)
    al.add_argument("--volume", type=float, default=2)
    al.add_argument("--categories")
    al.set_defaults(fn=cmd_alerts)
    rs = sub.add_parser("research", help="Pull research for one NSE ticker")
    rs.add_argument("symbol")
    rs.add_argument("--inputs", help="read saved exchange payloads from this directory instead of the network")
    rs.add_argument("--as-of", help="research as of this date (YYYY-MM-DD); default today")
    rs.add_argument("--out", default=str(WEB_RESEARCH))
    rs.add_argument("--llm", action="store_true", help="let a model reword credibility interpretations (kept only if it adds no number, cause, judgement or name to the cited facts)")
    rs.set_defaults(fn=cmd_research)
    rf = sub.add_parser("research-fixtures", help="build synthetic research fixtures and their reports")
    rf.add_argument("--fixtures", default=str(RESEARCH_FIXTURES))
    rf.add_argument("--out", default=str(WEB_RESEARCH))
    rf.set_defaults(fn=cmd_research_fixtures)
    ak = sub.add_parser("ask", help="ask a question of a built research report")
    ak.add_argument("symbol")
    ak.add_argument("question")
    ak.add_argument("--out", default=str(WEB_RESEARCH))
    ak.add_argument("--json", action="store_true")
    ak.set_defaults(fn=cmd_ask)
    sv = sub.add_parser("serve", help="on-demand research API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8787)
    sv.add_argument("--fixtures", default=str(RESEARCH_FIXTURES), help="serve fixture companies from this directory (if it exists)")
    sv.add_argument("--no-live", action="store_true", help="don't fetch live sources for other tickers")
    sv.add_argument("--out", default=str(WEB_RESEARCH))
    sv.add_argument("--llm", action="store_true", help="let a model write Ask FINN answers (each block checked against its citations)")
    sv.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
