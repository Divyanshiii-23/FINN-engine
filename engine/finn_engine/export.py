"""Feed export: the single JSON document the web app reads.

The feed always states which dataset it is ("live" or "fixture"), when it was
generated, which sources succeeded or failed, and which companies have gaps.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import CLASSIFIER_VERSION, EXTRACTOR_VERSION, SCORING_VERSION
from .config import Config
from .market import explaining_window, signal_at
from .materiality import BRIEF, CATEGORY_LABEL, INTERRUPT
from .pipeline import RunResult
from .store import Store
from .taxonomy import CATEGORIES

DATASET_NOTES = {
    "live": "Live data: filings from the exchanges and end-of-day prices from Yahoo Finance, as fetched by the pipeline.",
    "fixture": "Test fixtures: synthetic filings, prices and documents for fictional companies, generated to test the pipeline. These are not real exchange filings.",
}


def build_feed(cfg: Config, store: Store, result: RunResult, dataset: str, lookback_days: int = 30, as_of: datetime | None = None) -> dict:
    now = datetime.now(timezone.utc)
    events = store.events_since(now - timedelta(days=lookback_days)) if dataset == "live" else result.events
    if dataset == "fixture":
        events = result.events
    events.sort(key=lambda e: e.last_filed_at, reverse=True)

    # Source health
    health: dict[str, dict] = {}
    for l in result.logs:
        h = health.setdefault(l.source, {"source": l.source, "ok": 0, "failed": 0, "rows": 0, "errors": []})
        h["ok" if l.ok else "failed"] += 1
        h["rows"] += l.rows
        if not l.ok and l.error and len(h["errors"]) < 5:
            h["errors"].append(f"{l.target}: {l.error}")
    unavailable = [{"symbol": l.target, "source": l.source, "error": l.error} for l in result.logs if not l.ok and l.source in {"bse", "nse", "yahoo", "eod"}]

    companies = []
    market = []
    eod_dates = []
    for c in cfg.companies:
        bars, splits = result.bars.get(c.symbol, ([], set()))
        sig = signal_at(c.symbol, bars, splits) if bars else None
        explaining: list[str] = []
        if sig:
            eod_dates.append(sig.date)
            lo, hi = explaining_window(sig.date, bars)
            explaining = [e.id for e in events if e.symbol == c.symbol and not e.routine and any(lo < a.filed_at <= hi for a in e.announcements if not a.duplicate_of)]
            market.append({"symbol": c.symbol, "signal": json.loads(sig.model_dump_json()), "explaining_event_ids": explaining, "window": [lo.isoformat(), hi.isoformat()]})
        companies.append(
            {
                **json.loads(c.model_dump_json()),
                "eod": {"available": bool(bars), "bars": len(bars), "first": bars[0].date.isoformat() if bars else None, "last": bars[-1].date.isoformat() if bars else None},
                "closes": [{"date": b.date.isoformat(), "close": b.close, "adj_close": b.adj_close, "volume": b.volume} for b in bars[-90:]],
            }
        )

    filed = [e.last_filed_at for e in events]
    return {
        "schema": "finn.push.v1",
        "dataset": dataset,
        "dataset_note": DATASET_NOTES[dataset],
        "generated_at": now.isoformat(),
        "as_of": (as_of or now).isoformat(),
        "eod_date": max(eod_dates).isoformat() if eod_dates else None,
        "versions": {"scoring": SCORING_VERSION, "classifier": CLASSIFIER_VERSION, "extractor": EXTRACTOR_VERSION},
        "thresholds": {"interrupt": INTERRUPT, "brief": BRIEF},
        "categories": [{"id": k, "label": CATEGORY_LABEL.get(k, k), "description": v} for k, v in CATEGORIES.items()],
        "sources": list(health.values()),
        "unavailable": unavailable,
        "rejections": result.rejections,
        "companies": companies,
        "market": market,
        "events": [json.loads(e.model_dump_json()) for e in events],
    }


def write(feed: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    tmp.replace(path)
