"""Push-intelligence pipeline.

filing -> normalise -> de-duplicate -> classify -> cluster into events
       -> fetch attachment -> extract (results figures, facts)
       -> market reaction from EOD bars -> materiality -> explanation -> store

Inputs come from live adapters (BSE/NSE/Yahoo over HTTP) or from files
(importers). Every fetch is logged; failures are recorded and surfaced, never
filled in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Protocol

import pymupdf

from .classify import classify
from .config import Config
from .dedupe import cluster, dedupe, event_id, primary
from .explain import gemini_completer, llm_explain, template
from .extract.facts import extract_facts
from .extract.results import extract_pdf
from .market import reaction_session, signal_at
from .materiality import score
from .models import Announcement, Company, EodBar, Event, FetchLog, ResultsExtraction
from .sources import bse, nse, yahoo
from .sources.files import load_bse_rows, load_eod, load_nse_rows
from .sources.http import EXCHANGE_HOSTS, HttpClient
from .store import Store

IST = timezone(timedelta(hours=5, minutes=30))
MATERIAL_ATTACHMENT = {"results", "credit_rating", "management_change", "pledging", "mna", "capex", "fund_raise", "litigation", "press_release", "dividend"}


class Inputs(Protocol):
    fixture: bool

    def announcements(self, c: Company, start: date, end: date) -> tuple[list[dict], list[dict], list[FetchLog]]: ...
    def bars(self, c: Company) -> tuple[list[EodBar], set[date], FetchLog]: ...
    def attachment(self, url: str) -> tuple[bytes | None, str | None, FetchLog | None]: ...


class LiveInputs:
    fixture = False

    def __init__(self, client: HttpClient, use_nse: bool = False):
        self.client = client
        self.use_nse = use_nse

    def announcements(self, c, start, end):
        rows, logs = bse.fetch(self.client, c, start, end)
        nrows: list[dict] = []
        if self.use_nse:
            nrows, nlogs = nse.fetch(self.client, c, start, end)
            logs += nlogs
        return rows, nrows, logs

    def bars(self, c):
        data, log = yahoo.fetch(self.client, c.yahoo_symbol)
        if data is None:
            return [], set(), log
        try:
            b, s = yahoo.parse_chart(data)
            log.rows = len(b)
            return b, s, log
        except ValueError as e:
            log.ok, log.error = False, str(e)
            return [], set(), log

    def attachment(self, url):
        name = url.rsplit("/", 1)[-1]
        last = None
        for u in bse.attachment_urls(name) if "bseindia.com" in url else [url]:
            body, log = self.client.get("attachment", name, u, expect="bytes", headers={"Referer": "https://www.bseindia.com/"}, hosts=EXCHANGE_HOSTS)
            last = log
            if body:
                return body, None, log
        return None, f"attachment could not be downloaded ({last.error if last else 'no URL'})", last


class FileInputs:
    """Reads bse/<SYMBOL>.json, nse/<SYMBOL>.json, eod/<SYMBOL>.csv|json, attachments/<name>."""

    def __init__(self, root: Path, fixture: bool):
        self.root = root
        self.fixture = fixture

    def _log(self, source: str, target: str, path: Path, ok: bool, rows: int = 0, error: str | None = None) -> FetchLog:
        return FetchLog(source=source, target=target, url=f"file://{path}", ok=ok, rows=rows, error=error, fetched_at=datetime.now(timezone.utc), raw_path=str(path) if ok else None)

    def announcements(self, c, start, end):
        logs, brows, nrows = [], [], []
        p = self.root / "bse" / f"{c.symbol}.json"
        if p.exists():
            brows = load_bse_rows(p)
            logs.append(self._log("bse", c.symbol, p, True, len(brows)))
        else:
            logs.append(self._log("bse", c.symbol, p, False, error="no BSE announcements file for this company"))
        q = self.root / "nse" / f"{c.symbol}.json"
        if q.exists():
            nrows = load_nse_rows(q)
            logs.append(self._log("nse", c.symbol, q, True, len(nrows)))
        return brows, nrows, logs

    def bars(self, c):
        for ext in (".csv", ".json"):
            p = self.root / "eod" / f"{c.symbol}{ext}"
            if p.exists():
                b, s = load_eod(p)
                sp = self.root / "eod" / f"{c.symbol}.splits"
                if sp.exists():
                    s |= {date.fromisoformat(x.strip()) for x in sp.read_text().split() if x.strip()}
                return b, s, self._log("eod", c.symbol, p, True, len(b))
        p = self.root / "eod" / f"{c.symbol}.csv"
        return [], set(), self._log("eod", c.symbol, p, False, error="no end-of-day file for this company")

    def attachment(self, url):
        name = url.rsplit("/", 1)[-1]
        p = self.root / "attachments" / name
        if p.exists():
            return p.read_bytes(), None, self._log("attachment", name, p, True, 1)
        return None, "attachment file not available", self._log("attachment", name, p, False, error="not found")


def _pdf_text(body: bytes, pages: int = 2) -> str:
    try:
        doc = pymupdf.open(stream=body, filetype="pdf")
        return " ".join(doc[i].get_text() for i in range(min(pages, len(doc))))
    except Exception:  # noqa: BLE001
        return ""


@dataclass
class RunResult:
    run_id: int
    events: list[Event]
    announcements: list[Announcement]
    logs: list[FetchLog]
    rejections: list[str]
    bars: dict[str, tuple[list[EodBar], set[date]]] = field(default_factory=dict)


def run(cfg: Config, inputs: Inputs, store: Store, start: date, end: date, dataset: str, use_llm: bool = True) -> RunResult:
    run_id = store.start_run(dataset, start, end)
    logs: list[FetchLog] = []
    rejections: list[str] = []
    anns: list[Announcement] = []
    lo = datetime.combine(start, time.min, tzinfo=IST)
    hi = datetime.combine(end, time.max, tzinfo=IST)

    for c in cfg.companies:
        brows, nrows, l = inputs.announcements(c, start, end)
        logs += l
        a, rej = bse.to_announcements(brows, c, fixture=inputs.fixture)
        anns += a
        rejections += rej
        if nrows:
            a2, rej2 = nse.to_announcements(nrows, c, fixture=inputs.fixture)
            anns += a2
            rejections += rej2
    anns = [a for a in anns if lo <= a.filed_at <= hi]
    anns = dedupe(anns)
    store.put_announcements(anns)

    bars: dict[str, tuple[list[EodBar], set[date]]] = {}
    for c in cfg.companies:
        b, s, l = inputs.bars(c)
        logs.append(l)
        if b:
            store.put_bars(c.symbol, b, s)
        bars[c.symbol] = store.bars(c.symbol)  # merged with earlier runs

    completer = gemini_completer() if use_llm and not inputs.fixture else None
    classified = [(a, classify(a)) for a in anns]
    events: list[Event] = []
    for group in cluster(classified):
        a0, c0 = primary(group)
        comp = cfg.company(a0.symbol)
        text = " ".join(filter(None, [a0.subject, a0.headline]))
        results: ResultsExtraction | None = None
        attachment: dict | None = None
        if not c0.routine and c0.category in MATERIAL_ATTACHMENT:
            target = next((a for a, c in group if c.subtype in {"financial_results", "board_meeting_outcome"} and a.source.attachment_url), None) if c0.category == "results" else None
            target = target or (a0 if a0.source.attachment_url else None)
            if target and target.source.attachment_url:
                body, note, l = inputs.attachment(target.source.attachment_url)
                if l:
                    logs.append(l)
                attachment = {"status": "ok" if body else "unavailable", "url": target.source.attachment_url, "note": note, "announcement_id": target.id}
                if body:
                    text += " " + _pdf_text(body)
                    if c0.category == "results" and c0.subtype in {"financial_results", "board_meeting_outcome"}:
                        results = extract_pdf(body, is_financial=comp.is_financial)
                elif c0.category == "results" and c0.subtype in {"financial_results", "board_meeting_outcome"}:
                    results = ResultsExtraction(status="unavailable", reason=note)
            else:
                attachment = {"status": "none", "url": None, "note": "filing has no attachment", "announcement_id": a0.id}
        facts = extract_facts(c0.category, c0.subtype, text)
        if c0.category == "management_change" and len(group) > 1:
            for a, c in group:
                f1 = extract_facts(c.category, c.subtype, " ".join(filter(None, [a.subject, a.headline])))
                if f1.person or f1.role:
                    facts.changes.append({"action": (f1.person_action or c.subtype or "change").replace("_", " "), "person": f1.person, "role": f1.role, "announcement_id": a.id})

        b, s = bars.get(a0.symbol, ([], set()))
        session = reaction_session(a0.filed_at, b) if b else None
        reaction = signal_at(a0.symbol, b, s, session) if session else None
        pending = bool(b) and session is None

        m = score(comp, c0, facts, results, reaction, pending)
        expl = template(c0, facts, results, m, a0.subject, a0.headline, comp.is_financial)
        if completer and not c0.routine:
            complete, model = completer
            inputs_for_llm = {"category": c0.category, "subtype": c0.subtype, "facts": facts.model_dump(exclude_none=True), "drivers": [c.detail for c in m.components if c.points > 0]}
            try:
                expl = llm_explain(expl, inputs_for_llm, complete, model)
            except Exception as e:  # noqa: BLE001
                expl = expl.model_copy(update={"rejected_llm_reason": f"LLM call failed: {type(e).__name__}"})

        filed = [a.filed_at for a, _ in group]
        events.append(
            Event(
                id=event_id(group),
                symbol=a0.symbol,
                category=c0.category,
                subtype=c0.subtype,
                routine=c0.routine,
                title=expl.what if len(expl.what) <= 150 else expl.what[:149] + "…",
                first_filed_at=min(filed),
                last_filed_at=max(filed),
                announcements=[a for a, _ in sorted(group, key=lambda x: x[0].filed_at)] + [d for d in anns if d.duplicate_of in {a.id for a, _ in group}],
                classification=c0,
                facts=facts,
                results=results,
                reaction=reaction,
                reaction_session=session,
                materiality=m,
                explanation=expl,
                attachment=attachment,
                fixture=inputs.fixture,
            )
        )
    store.put_events(events)
    store.log(run_id, logs)
    store.finish_run(run_id, {"announcements": len(anns), "duplicates": sum(1 for a in anns if a.duplicate_of), "events": len(events), "rejections": rejections})
    return RunResult(run_id=run_id, events=events, announcements=anns, logs=logs, rejections=rejections, bars=bars)
