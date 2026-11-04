"""Runs areas A, B, C (except C4) and E against a fresh build of the real pipelines.

    python eval/run_engine_eval.py [label]

1. builds the research fixtures and runs the Pull pipeline for every company (as `finn research-fixtures` does)
2. starts the research HTTP service and asks every question through it (as the web app does)
3. builds the push fixtures and runs the push pipeline into a feed (as `finn fixtures` does)
4. scores the outputs against the gold sets in eval/gold and independent recomputation
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "engine"))

import eval_data  # noqa: E402
import eval_push  # noqa: E402
import eval_research  # noqa: E402
from harness import Recorder  # noqa: E402

from finn_engine import fixtures as FX  # noqa: E402
from finn_engine.config import ENGINE_DIR, load  # noqa: E402
from finn_engine.export import build_feed  # noqa: E402
from finn_engine.pipeline import FileInputs as PushInputs  # noqa: E402
from finn_engine.pipeline import run as push_run  # noqa: E402
from finn_engine.research import fixtures as RF  # noqa: E402
from finn_engine.research import pipeline as RP  # noqa: E402
from finn_engine.research.service import Inputs, Service, handler  # noqa: E402
from finn_engine.research.sources import FileInputs  # noqa: E402
from finn_engine.store import Store  # noqa: E402

SYMBOLS = ["HALCYON", "KAVERI", "SARANG", "VEDIKA", "CORAL"]


def main(label: str) -> int:
    rec = Recorder("engine")
    work = Path(tempfile.mkdtemp(prefix="finn-eval-"))
    RF.build(work / "inputs")
    inp = FileInputs(work / "inputs")
    out = work / "reports"
    for s in SYMBOLS:
        RP.write(RP.run(s, inp, as_of=RF.AS_OF), out)
    reps = {s: json.loads((out / f"{s}.json").read_text()) for s in SYMBOLS}
    passages = {s: json.loads((out / f"{s}.passages.json").read_text()) for s in SYMBOLS}

    svc = Service(Inputs(None, inp), out)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(svc))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def ask_http(sym: str, q: str) -> dict:
        req = urllib.request.Request(f"{base}/v1/ask/{sym}", data=json.dumps({"question": q}).encode(), method="POST", headers={"Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            return {"status": f"http_{e.code}", "blocks": [], "error": e.read().decode()[:200]}

    # Push pipeline
    pdir = work / "push"
    FX.build(ENGINE_DIR, pdir)
    cfg = load(ENGINE_DIR / "fixtures" / "universe.yaml")
    store = Store(work / "push.db")
    res = push_run(cfg, PushInputs(pdir, fixture=True), store, FX.FIXTURE_FROM, FX.FIXTURE_TO, "fixture", use_llm=False)
    feed = json.loads(json.dumps(build_feed(cfg, store, res, "fixture", as_of=FX.as_of()), default=str))
    (work / "feed.json").write_text(json.dumps(feed))

    for mod, args in ((eval_data, (rec, reps, work / "inputs")), (eval_research, (rec, reps, passages, ask_http)), (eval_push, (rec, feed))):
        try:
            mod.run(*args)
        except Exception as e:  # noqa: BLE001 - a crash in one area is itself a result
            import traceback
            rec.check(mod.__name__[5:6].upper() if mod is not eval_research else "B", f"{mod.__name__} crashed", type(e).__name__, False, traceback.format_exc()[-800:], severity="critical")
    srv.shutdown()
    p = rec.save(label)
    print(rec.summary())
    fails = [c for c in rec.checks if not c.passed]
    print(f"\n{len(rec.checks) - len(fails)}/{len(rec.checks)} checks passed; {sum(c.severity == 'critical' for c in fails)} critical failures; results in {p}; work dir {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "baseline"))
