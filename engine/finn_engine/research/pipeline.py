"""Pull research for one NSE ticker: resolve → discover → parse → join → sections."""

from __future__ import annotations

import hashlib
import contextlib
import threading
import os
import tempfile
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .. import EXTRACTOR_VERSION
from ..sources import bse as bse_src
from ..sources import nse as nse_src
from . import CLAIMS_VERSION, RESEARCH_VERSION
from . import narrative as N
from . import periods as P
from . import sections as S
from . import statements as ST
from .financials import Facts, Numbers
from . import ask as ASK
from . import credibility as CR
from .ledger import Ledger, claim_fact, discrepancies
from .models import Claim, Doc, Gap, Identity
from .pdftext import read as read_pdf
from .sources import ResearchInputs

SCHEMA = "finn.research.v1"
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")
FIN_NAME = re.compile(r"\bbank\b|\bfinance\b|\bfinancial services\b|\bfincorp\b|\bfinserv\b|\bhousing finance\b|\bnbfc\b", re.I)
FIN_INDUSTRY = re.compile(r"bank|financ|nbfc|lending|housing finance|microfinance|credit", re.I)
IT_INDUSTRY = re.compile(r"\bit\b|software|computers|information technology|it services|it enabled", re.I)
# Credibility needs closed periods: ten quarters of results and calls cover about three fiscal years of promises.
HISTORY_QUARTERS = 10
ANNUAL_REPORTS = 3
WINDOW_DAYS = 1000


class ResearchError(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def normalise(symbol: str) -> str:
    s = symbol.strip().upper().removesuffix(".NS").removeprefix("NSE:")
    if not SYMBOL.match(s):
        raise ResearchError("INVALID_SYMBOL", f"'{symbol}' isn't an NSE symbol (letters, digits, & and - only).")
    return s


# ------------------------------------------------------------------ resolve

def resolve(symbol: str, inputs: ResearchInputs, logs: list) -> Identity:
    master, log = inputs.equity_master()
    logs.append(log)
    row = next((r for r in master if r.get("SYMBOL", "").upper() == symbol), None)
    idn: Identity | None = None
    seed = "seed copy" in (log.target or "")
    if row:
        idn = Identity(symbol=symbol, name=row.get("NAME OF COMPANY", symbol), isin=row.get("ISIN NUMBER") or row.get(" ISIN NUMBER"),
                       series=row.get("SERIES"), listed_on=row.get("DATE OF LISTING"), sources=[log.target if seed else "NSE equity master"])
        if seed:
            idn.notes.append("Ticker checked against a November 2023 copy of NSE's equity list because NSE couldn't be reached; name and ISIN may have changed since.")
    else:
        meta, log = inputs.nse_meta(symbol)
        logs.append(log)
        if meta:
            if meta.get("isDelisted") == "true":
                raise ResearchError("DELISTED", f"{symbol} is delisted on NSE.")
            idn = Identity(symbol=symbol, name=meta.get("companyName", symbol), isin=meta.get("isin"), series=(meta.get("activeSeries") or [None])[0], sources=["NSE quote meta-info"])
    if not idn:
        if not master:
            raise ResearchError("SOURCES_UNAVAILABLE", "Couldn't reach NSE to check the ticker. Try again later, or run with --inputs for saved files.")
        if seed and not log.ok:
            raise ResearchError("UNVERIFIED_SYMBOL", f"{symbol} isn't in the November 2023 copy of NSE's list, and NSE couldn't be reached to check newer listings.")
        raise ResearchError("UNKNOWN_SYMBOL", f"{symbol} isn't in NSE's list of listed equities.")
    if idn.series and idn.series not in ("EQ", "BE", "BZ", "SM", "ST"):
        idn.notes.append(f"Series {idn.series}: not a regular equity series.")
    scrips, log = inputs.bse_scrips()
    logs.append(log)
    s = next((r for r in scrips if idn.isin and r.get("ISIN_NUMBER") == idn.isin), None)
    if s:
        idn.bse_code = str(s.get("SCRIP_CD"))
        idn.bse_name = s.get("Scrip_Name") or s.get("Issuer_Name")
        idn.industry = s.get("INDUSTRY")
        idn.sources.append("BSE scrip list (matched on ISIN)")
        if idn.bse_name and not bse_src.name_matches(idn.name, idn.bse_name):
            idn.notes.append(f"BSE lists ISIN {idn.isin} as '{idn.bse_name}', which doesn't match NSE's '{idn.name}'. Check before relying on BSE filings.")
        try:
            idn.market_cap_cr = float(s["Mktcap"]) if s.get("Mktcap") else None
        except (TypeError, ValueError):
            pass
    elif not scrips:
        idn.notes.append("BSE's scrip list couldn't be fetched, so BSE filings weren't searched.")
    else:
        idn.notes.append("No BSE listing found for this ISIN; filings can only come from NSE.")
    idn.is_financial = bool(idn.industry and FIN_INDUSTRY.search(idn.industry))
    if not idn.industry and FIN_NAME.search(idn.name or ""):
        # Without BSE's industry field a bank would otherwise be analysed like a manufacturer (EBITDA on interest income).
        idn.is_financial = True
        idn.notes.append(f"Industry unknown (BSE's scrip list wasn't available); treated as a lender because the name is '{idn.name}'.")
    idn.is_it_services = bool(idn.industry and IT_INDUSTRY.search(idn.industry))
    return idn


# ------------------------------------------------------------------ discover

KIND_RULES: list[tuple[str, re.Pattern[str], re.Pattern[str] | None]] = [
    ("transcript", re.compile(r"transcript", re.I), None),
    ("presentation", re.compile(r"(investor|earnings|analyst|results?)\s+presentation|presentation (to|for) (investors|analysts)", re.I), re.compile(r"schedule|intimation of (meeting|analyst)", re.I)),
    ("annual_report", re.compile(r"annual report", re.I), re.compile(r"business responsibility|brsr|sustainability|notice|newspaper", re.I)),
    ("press_release", re.compile(r"press release|media release", re.I), None),
    ("results", re.compile(r"financial results?|results for the (quarter|period|year)", re.I), re.compile(r"intimation|to consider|board meeting on|newspaper|publication|corrigendum|trading window|closure|record date|audio|recording", re.I)),
]
QEND_TEXT = re.compile(r"(?:quarter|period|half year|year|nine months)\s+ended\s+(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?[\s.\-/]*(sep(?:tember)?|dec(?:ember)?|mar(?:ch)?|jun(?:e)?|0?9|12|0?3|0?6)[\s.,\-/]*(20\d{2})", re.I)
QLABEL_TEXT = re.compile(r"\b(q[1-4])\s?[-']?\s?fy\s?'?(?:20)?(\d{2})\b", re.I)
FYLABEL_TEXT = re.compile(r"\b20(\d{2})\s?-\s?(?:20)?(\d{2})\b|\bfy\s?'?(?:20)?(\d{2})\b", re.I)
MON = {"sep": 9, "dec": 12, "mar": 3, "jun": 6, "9": 9, "09": 9, "12": 12, "3": 3, "03": 3, "6": 6, "06": 6}


def _last_quarter_before(d: date) -> str:
    fy, q = P.quarter_of(d)
    return P.prev_q(P.qlabel(fy, q))


def infer_period(kind: str, text: str, filed: date | None) -> tuple[str | None, str]:
    m = QLABEL_TEXT.search(text)
    if m and kind != "annual_report":
        return f"{m.group(1).upper()} FY{m.group(2)}", "stated in the filing subject"
    m = QEND_TEXT.search(text)
    if m and kind != "annual_report":
        mo = MON.get(m.group(2).lower()[:3], MON.get(m.group(2).lower()))
        try:
            lab = P.label_for_end(date(int(m.group(3)), mo, 28 if mo != 12 else 31).replace(day={9: 30, 12: 31, 3: 31, 6: 30}[mo]))  # type: ignore[arg-type]
            if lab:
                return lab, "quarter-end date in the filing subject"
        except (KeyError, ValueError, TypeError):
            pass
    if kind == "annual_report":
        m = FYLABEL_TEXT.search(text)
        if m:
            return f"FY{m.group(2) or m.group(3)}", "financial year in the filing subject"
        if filed:
            return f"FY{(P.fy_of(filed) - 1) % 100:02d}", "inferred: annual reports are filed after the year they cover"
        return None, "unknown"
    if filed:
        return _last_quarter_before(filed), "inferred: the last quarter ended before the filing date"
    return None, "unknown"


def classify_row(text: str) -> str | None:
    for kind, inc, exc in KIND_RULES:
        if inc.search(text) and not (exc and exc.search(text)):
            if kind == "press_release" and not re.search(r"result|quarter|financial performance|earnings", text, re.I):
                return None
            return kind
    return None


def discover(idn: Identity, inputs: ResearchInputs, as_of: date, logs: list, rejections: list[str], fixture: bool) -> list[Doc]:
    start = as_of - timedelta(days=WINDOW_DAYS)
    cands: list[Doc] = []
    if idn.bse_code:
        rows, ls = inputs.announcements(idn.bse_code, idn.name, start, as_of)
        logs.extend(ls)
        for r in rows:
            filer = (r.get("SLONGNAME") or "").strip()
            if filer and not bse_src.name_matches(idn.name, filer):
                rejections.append(f"BSE row {r.get('NEWSID')}: filer '{filer}' doesn't match {idn.name}")
                continue
            text = " | ".join(str(r.get(k) or "") for k in ("NEWSSUB", "HEADLINE", "SUBCATNAME", "CATEGORYNAME"))
            kind = classify_row(text)
            att = (r.get("ATTACHMENTNAME") or "").strip()
            if not kind:
                continue
            filed = bse_src.parse_time(r.get("DissemDT")) or bse_src.parse_time(r.get("DT_TM"))
            per, basis = infer_period(kind, text, filed.date() if filed else None)
            sid = str(r.get("NEWSID"))
            cands.append(Doc(
                id="d:" + hashlib.sha1(f"bse:{sid}".encode()).hexdigest()[:10], kind=kind, title=re.sub(r"^.*?\s-\s\d{5,6}\s-\s", "", (r.get("NEWSSUB") or kind).strip())[:160], period=per, period_basis=basis,
                filed_at=filed, source="bse", source_id=sid,
                url=None if fixture else (bse_src.attachment_urls(att)[0] if att else None), listing_url=None if fixture else r.get("NSURL"),
                raw_path=r.get("_raw_path"), fixture=fixture,
                status="unavailable" if not att else "not_used", status_reason=None if att else "filing has no attachment",
                parse={"attachment": att or None, "subcategory": r.get("SUBCATNAME"), "is_results_category": bool(re.search(r"result", str(r.get("CATEGORYNAME") or "") + str(r.get("SUBCATNAME") or ""), re.I))},
            ))
    rows, ls = inputs.nse_announcements(idn.symbol, idn.name, start, as_of)
    logs.extend(ls)
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        filer = (r.get("sm_name") or "").strip()
        if sym and sym != idn.symbol or filer and not bse_src.name_matches(idn.name, filer):
            rejections.append(f"NSE row {r.get('seq_id')}: filer '{filer or sym}' doesn't match {idn.name}")
            continue
        text = " | ".join(str(r.get(k) or "") for k in ("desc", "attchmntText"))
        kind = classify_row(text)
        if not kind:
            continue
        att = (r.get("attchmntFile") or "").strip()
        filed = nse_src.parse_time(r)
        per, basis = infer_period(kind, text, filed.date() if filed else None)
        sid = str(r.get("seq_id"))
        cands.append(Doc(
            id="d:" + hashlib.sha1(f"nse:{sid}".encode()).hexdigest()[:10], kind=kind, title=(r.get("attchmntText") or r.get("desc") or kind).strip()[:160],
            period=per, period_basis=basis, filed_at=filed, source="nse", source_id=sid,
            url=None if fixture else (att or None), raw_path=r.get("_raw_path"), fixture=fixture,
            status="unavailable" if not att else "not_used", status_reason=None if att else "filing has no attachment",
            parse={"attachment": att or None, "is_results_category": "result" in str(r.get("desc") or "").lower()},
        ))
    ars, log = inputs.annual_reports(idn.symbol)
    logs.append(log)
    for r in ars:
        fn = r.get("fileName") or ""
        if not fn.lower().endswith(".pdf"):
            continue
        fy = f"FY{str(r.get('toYr', ''))[-2:]}" if r.get("toYr") else None
        try:
            filed = datetime.strptime(r.get("broadcast_dttm", ""), "%d-%b-%Y %H:%M:%S").replace(tzinfo=bse_src.IST)
        except ValueError:
            filed = None
        cands.append(Doc(id="d:" + hashlib.sha1(f"nse-ar:{fn}".encode()).hexdigest()[:10], kind="annual_report", title=f"Annual report {r.get('fromYr')}-{r.get('toYr')}",
                         period=fy, period_basis="financial year in the NSE annual-report record", filed_at=filed, source="nse", url=None if fixture else fn,
                         fixture=fixture, status="not_used", parse={"attachment": fn}))
    for d in inputs.ir_documents(idn.symbol):
        ref = d.get("file") or d.get("url")
        cands.append(Doc(id="d:" + hashlib.sha1(f"ir:{ref}".encode()).hexdigest()[:10], kind=d["kind"], title=d.get("title") or Path(str(ref)).name, period=d.get("period"),
                         period_basis="given with the document", filed_at=datetime.fromisoformat(d["date"]) if d.get("date") else None, source="company_ir",
                         url=None if fixture else d.get("url"), fixture=fixture, status="not_used", parse={"attachment": ref, "trusted": True}))
    return select(cands)


def select(cands: list[Doc]) -> list[Doc]:
    """Latest ten results quarters; one transcript and presentation per quarter; the latest three annual reports."""
    def newest(ds: list[Doc]) -> Doc:
        return sorted(ds, key=lambda d: (d.status != "unavailable", d.parse.get("is_results_category", False), d.filed_at or datetime.min.replace(tzinfo=timezone.utc)))[-1]
    def pick(ds: list[Doc]) -> Doc:
        # The same document is usually filed on both exchanges: keep one, and the others as fallbacks.
        best = newest(ds)
        best.parse["alternates"] = [{"source": d.source, "source_id": d.source_id, "attachment": d.parse.get("attachment")}
                                    for d in ds if d is not best and d.parse.get("attachment")]
        return best
    out: list[Doc] = []
    res: dict[str, list[Doc]] = {}
    for d in cands:
        if d.kind == "results" and d.period and d.period.startswith("Q"):
            res.setdefault(d.period, []).append(d)
    quarters = sorted(res, key=P.q_index)[-HISTORY_QUARTERS:]
    for q in quarters:
        out.append(pick(res[q]))
    window = set(quarters) or {d.period for d in cands if d.period}
    for kind in ("transcript", "presentation", "press_release"):
        per: dict[str, list[Doc]] = {}
        for d in cands:
            if d.kind == kind and d.period in window:
                per.setdefault(d.period, []).append(d)  # type: ignore[arg-type]
        out += [pick(v) for v in per.values()]
    by_year: dict[str, list[Doc]] = {}
    for d in cands:
        if d.kind == "annual_report":
            by_year.setdefault(d.period or "", []).append(d)
    for year in sorted(by_year)[-ANNUAL_REPORTS:]:
        out.append(pick(sorted(by_year[year], key=lambda d: (d.source == "bse", d.filed_at or datetime.min.replace(tzinfo=timezone.utc)))))
    return out


# ------------------------------------------------------------------ run

def run(symbol: str, inputs: ResearchInputs, as_of: date | None = None, progress: Callable[[str], None] | None = None,
        rephrase: Callable[[str, str], str | None] | None = None) -> dict:
    say = progress or (lambda s: None)
    as_of = as_of or date.today()
    logs: list = []
    rejections: list[str] = []
    gaps: list[Gap] = []
    sym = normalise(symbol)
    say("resolve")
    idn = resolve(sym, inputs, logs)
    fixture = inputs.dataset == "fixture"
    say("discover")
    n_logs = len(logs)
    docs = discover(idn, inputs, as_of, logs, rejections, fixture)
    disc_logs = [l for l in logs[n_logs:] if l]
    if not docs and disc_logs and not any(l.ok for l in disc_logs):
        raise ResearchError("SOURCES_UNAVAILABLE", f"None of the filing sources for {sym} could be reached, so there is nothing to research yet.",
                            detail={"identity": idn.model_dump(), "fetch_log": [l.model_dump(mode="json") for l in logs if l]})
    facts = Facts()

    say("download")
    blobs: dict[str, bytes] = {}
    for d in docs:
        ref = d.parse.get("attachment")
        if not ref:
            continue
        trusted = bool(d.parse.get("trusted"))
        body, log = inputs.download(ref if trusted else ("fixture://" + ref) if fixture else ref, trusted=trusted)
        logs.append(log)
        for alt in d.parse.get("alternates", []) if body is None else []:
            body, log = inputs.download(("fixture://" + alt["attachment"]) if fixture else alt["attachment"])
            logs.append(log)
            if body is not None:
                d.parse["downloaded_from"] = f"{alt['source']} copy ({alt['source_id']})"
                break
        if body is None:
            d.status, d.status_reason = "unavailable", f"attachment couldn't be fetched ({log.error})" if log else "attachment couldn't be fetched"
            continue
        d.sha256 = hashlib.sha256(body).hexdigest()
        d.fetched_at = log.fetched_at
        d.raw_path = log.raw_path or d.raw_path
        blobs[d.id] = body

    say("numbers")
    passages: list[dict] = []
    filings = []
    for d in docs:
        if d.kind != "results" or d.id not in blobs:
            continue
        st = ST.parse(blobs[d.id], idn.is_financial)
        d.parse.update({"basis": st.basis, "unit": st.unit, "checks": st.checks, "statements": [k for k, v in (("P&L", st.pnl), ("Balance sheet", st.bs), ("Cash flow", st.cf), ("Segment note", st.segments)) if v]})
        if st.status == "failed":
            d.status, d.status_reason = "failed", st.reason
            continue
        if st.current and st.current != d.period:
            d.parse["listing_period"] = d.period
            d.period, d.period_basis = st.current, "header dates in the results statement"
        d.status = "parsed"
        d.status_reason = st.reason
        passages += ASK.build_passages(d, read_pdf(blobs[d.id]))
        try:
            import pymupdf
            d.pages = len(pymupdf.open(stream=blobs[d.id], filetype="pdf"))
        except Exception:  # noqa: BLE001
            pass
        filings.append((d, st))
    numbers = Numbers.build(facts, filings, idn.is_financial)
    if not filings:
        gaps.append(Gap(area="Numbers", detail="No results filing could be read, so no reported figures are shown and no guidance can be checked."))

    say("narrative")
    seg_names = sorted({s for q in numbers.seg.values() for s in q})
    ctx = {"threads": set(), "is_financial": idn.is_financial, "is_it": idn.is_it_services, "segments": seg_names}
    claims: list[Claim] = []
    overview = None
    complete_calls: list[Doc] = []
    narrative_docs = sorted([d for d in docs if d.kind in ("transcript", "presentation", "annual_report", "press_release") and d.id in blobs],
                            key=lambda d: d.filed_at or datetime.min.replace(tzinfo=timezone.utc))
    for d in narrative_docs:
        pdf = read_pdf(blobs[d.id])
        d.pages = pdf.pages
        if pdf.pages and len(pdf.scanned_pages) == pdf.pages:
            d.status, d.status_reason = "failed", "no text layer: every page is a scanned image (OCR is not enabled)"
            continue
        passages += ASK.build_passages(d, pdf)
        if d.kind == "transcript":
            cs, info = N.from_transcript(d, pdf, ctx)
            if info["complete"]:
                complete_calls.append(d)
        else:
            cs, info = N.from_document(d, pdf, ctx)
        if d.kind in ("annual_report", "presentation") and (overview is None or d.kind == "annual_report"):
            ov = N.business_overview(d, pdf)
            if ov:
                overview = (*ov, d)
        d.parse.update({k: v for k, v in info.items() if k != "roster"} | ({"roster": [f"{k.title()}: {v}" for k, v in info.get("roster", {}).items()]} if d.kind == "transcript" else {}))
        d.parse["claims"] = {k: sum(1 for c in cs if c.kind == k) for k in ("guidance", "assertion", "outlook")}
        d.status = "parsed"
        if pdf.scanned_pages:
            d.status_reason = f"pages {', '.join(map(str, pdf.scanned_pages))} are scanned images and weren't read"
        dmap = {x.id: x for x in docs}
        for c in cs:
            claim_fact(facts, c, dmap[c.doc_id])
        claims += cs
    transcripts = [d for d in docs if d.kind == "transcript"]
    if not transcripts:
        gaps.append(Gap(area="Narrative vs Numbers", detail="No earnings-call transcript was found on the exchange for the quarters read, so management guidance comes only from presentations and the annual report, if any."))
    for q in sorted({d.period for d in docs if d.kind == "results" and d.status == "parsed" and d.period}, key=P.q_index):
        if not any(t.period == q and t.status == "parsed" for t in transcripts):
            gaps.append(Gap(area="Coverage", detail=f"No readable {q} call transcript; threads aren't marked 'not repeated' on the strength of a missing call."))

    say("ledger")
    dmap = {d.id: d for d in docs}
    lg = Ledger(facts, numbers, dmap, idn.is_financial)
    lg.build_guidance(claims, sorted(complete_calls, key=lambda d: d.filed_at or datetime.min.replace(tzinfo=timezone.utc)))
    lg.build_assertions(claims)
    lg.build_shifts(claims)
    disc = discrepancies(lg)

    say("credibility")
    credibility = CR.build(lg, numbers, dmap, claims, idn.is_financial, rephrase)

    say("index")
    # Figures Ask FINN reads without the statements: cost lines as a share of revenue, quarterly margins.
    cost_lines = ASK.cost_lines(numbers, numbers.quarters(), idn.is_financial)
    if not idn.is_financial:
        for q in numbers.quarters():
            for num in ("ebit", "ebitda"):
                numbers.margin(q, num)
                numbers.margin_change(q, P.shift_year(q), num)
                numbers.margin_change(q, P.prev_q(q), num)

    say("sections")
    mcap = idn.market_cap_cr
    cash = S.cash_quality(numbers, idn.is_financial)
    sections = {
        "business": S.business(idn, numbers, overview, facts),
        "snapshot": S.snapshot(numbers, idn.is_financial, (mcap, "BSE scrip list") if mcap else None, facts),
        "trajectory": S.trajectory(numbers, idn.is_financial),
        "balance_sheet": S.balance_sheet(numbers, idn.is_financial),
        "cash_quality": cash,
        "nvn": {
            "entries": [e.id for e in sorted(lg.entries, key=lambda e: (-e.severity, e.kind != "guidance"))],
            "shifts": [s.model_dump() for s in lg.shifts],
            "discrepancies": [p.model_dump() for p in disc],
            "calls": [{"doc_id": d.id, "period": d.period, "complete": d in complete_calls} for d in sorted(transcripts, key=lambda d: P.q_index(d.period) if d.period and d.period.startswith("Q") else 0)],
        },
        "guidance": S.guidance_section(lg, claims, dmap),
        "bull_bear": S.bull_bear(numbers, lg, idn.is_financial, cash.get("flags")),
    }
    counts = {
        "documents": {k: sum(1 for d in docs if d.kind == k and d.status == "parsed") for k in ("results", "transcript", "presentation", "annual_report", "press_release")},
        "claims": {k: sum(1 for c in claims if c.kind == k) for k in ("guidance", "assertion", "outlook")},
        "claims_rejected_by_gates": sum(int(d.parse.get("claims_rejected_by_gates", 0)) for d in docs),
        "verdicts": {},
    }
    for e in lg.entries:
        counts["verdicts"][e.verdict] = counts["verdicts"].get(e.verdict, 0) + 1
    # Contract: every fact referenced by a section or ledger entry exists, and every fact is traceable.
    referenced = _referenced(sections, lg)
    missing = sorted(x for x in referenced if x not in facts.items)
    if missing:
        raise RuntimeError(f"internal: unresolved evidence ids {missing[:5]}")
    audit = audit_facts(facts, {d.id: d for d in docs}, sections, credibility)
    return {
        "schema": SCHEMA,
        "dataset": inputs.dataset,
        "dataset_note": "SYNTHETIC TEST FIXTURE: fictional company and documents; not a real filing." if fixture else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of.isoformat(),
        "versions": {"research": RESEARCH_VERSION, "claims": CLAIMS_VERSION, "statements": EXTRACTOR_VERSION},
        "identity": idn.model_dump(),
        "documents": [d.model_dump(mode="json") for d in sorted(docs, key=lambda d: (d.kind, d.period or ""))],
        "counts": counts,
        "facts": {k: v.model_dump(exclude_none=True) for k, v in facts.items.items()},
        "claims": [c.model_dump(exclude_none=True) for c in claims],
        "ledger": [e.model_dump(exclude_none=True) for e in lg.entries],
        "sections": sections,
        "credibility": credibility,
        "cost_lines": cost_lines,
        "passages": passages,
        "audit": audit,
        "restatements": numbers.restated,
        "checks": numbers.checks,
        "gaps": [g.model_dump() for g in gaps],
        "rejections": rejections,
        "fetch_log": [l.model_dump(mode="json") for l in logs if l],
    }


CRED_FACT_KEYS = {"fact", "actual", "execution", "ocf_pat", "ocf_ebitda", "fcf"}
CRED_LIST_KEYS = {"evidence", "management_said"}


def _cred_refs(x, out: set[str]) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            if k in CRED_FACT_KEYS and isinstance(v, str):
                out.add(v)
            elif k in CRED_LIST_KEYS and isinstance(v, list):
                out.update(i for i in v if isinstance(i, str))
            else:
                _cred_refs(v, out)
    elif isinstance(x, list):
        for i in x:
            _cred_refs(i, out)


def audit_facts(facts: Facts, docs: dict[str, Doc], sections: dict, credibility: dict | None = None) -> dict:
    """Checks the traceability contract and returns its summary. Violations raise.

    reported   → a parsed document, a page, and the row as printed
    quotes     → a parsed document, a page, and text that passed the on-page gate
    computed   → a formula and inputs that are themselves facts
    points     → at least one cited fact (bull/bear, discrepancies)
    """
    problems: list[str] = []
    n = {"reported": 0, "quotes": 0, "computed": 0, "market": 0, "points": 0}
    for f in facts.items.values():
        if f.info_class == "reported" and f.id.startswith("m:"):
            n["market"] += 1
            continue
        if f.info_class == "reported" and f.quote is None:
            n["reported"] += 1
            d = docs.get(f.doc_id or "")
            if not (d and d.status == "parsed" and f.page and f.row_text):
                problems.append(f"{f.id}: reported figure without document/page/row")
        elif f.quote is not None:
            n["quotes"] += 1
            d = docs.get(f.doc_id or "")
            if not (d and d.status == "parsed" and f.page):
                problems.append(f"{f.id}: quote without document/page")
        elif f.info_class == "computed":
            n["computed"] += 1
            if not f.formula or not f.inputs or any(i not in facts.items for i in f.inputs):
                problems.append(f"{f.id}: computed figure without formula or resolvable inputs")
    for key in ("discrepancies",):
        for p in sections["nvn"][key]:
            n["points"] += 1
            if not p["evidence"]:
                problems.append(f"{p['id']}: point without evidence")
    for side in ("bull", "bear"):
        for p in sections["bull_bear"][side]:
            n["points"] += 1
            if not p["evidence"]:
                problems.append(f"{p['id']}: point without evidence")
    if credibility is not None:
        refs: set[str] = set()
        _cred_refs(credibility, refs)
        problems += [f"credibility cites unknown fact {r}" for r in sorted(refs) if r not in facts.items][:5]
        for p in credibility["interpretation"]:
            n["points"] += 1
            if not p["evidence"]:
                problems.append(f"{p['id']}: interpretation without evidence")
    if problems:
        raise RuntimeError("internal: evidence contract violated: " + "; ".join(problems[:5]))
    return {**n, "ok": True}


def _referenced(sections: dict, lg: Ledger) -> set[str]:
    out: set[str] = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("fact", "value", "qoq", "yoy", "yoy_change", "growth_fact", "description", "revenue", "pat", "ebitda", "ebitda_margin", "revenue_growth") and isinstance(v, str):
                    out.add(v)
                elif k in ("evidence", "facts", "values") and isinstance(v, list):
                    out.update(i for i in v if isinstance(i, str))
                elif k == "series" and isinstance(v, dict):
                    for s in v.values():
                        out.update(i for i in s if isinstance(i, str))
                else:
                    walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    walk(sections)
    for e in lg.entries:
        out.update(x for x in e.evidence if x)
        out.update(x for x in (e.actual_fact, e.required_fact) if x)
        out.update(h.fact_id for h in e.history if h.fact_id)
    return out


def write(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sym = report["identity"]["symbol"]
    p = out_dir / f"{sym}.json"
    passages = report.pop("passages", [])
    _atomic_write(p, json.dumps(report, indent=1, default=str))
    # Passages for Ask FINN and document navigation live next to the report, not in it.
    pp = out_dir / f"{sym}.passages.json"
    _atomic_write(pp, json.dumps(passages, separators=(",", ":")))
    report["passages"] = passages
    idx_p = out_dir / "index.json"
    with _INDEX_LOCK, _file_lock(out_dir / ".index.lock"):  # concurrent jobs must not drop each other's entries
        _update_index(idx_p, sym, report)
    return p


_INDEX_LOCK = threading.Lock()


@contextlib.contextmanager
def _file_lock(path: Path):
    """Advisory lock across processes (CLI and service writing the same directory)."""
    with open(path, "a+") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:  # non-POSIX: the thread lock still applies
            pass
        yield


def _update_index(idx_p: Path, sym: str, report: dict) -> None:
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {"companies": []}
    idx["companies"] = [c for c in idx["companies"] if c["symbol"] != sym] + [{
        "symbol": sym, "name": report["identity"]["name"], "industry": report["identity"].get("industry"), "dataset": report["dataset"],
        "as_of": report["as_of"], "generated_at": report["generated_at"], "documents": report["counts"]["documents"],
        "flags": sum(1 for d in report["sections"]["nvn"]["discrepancies"] if d["severity"] >= 2),
    }]
    idx["companies"].sort(key=lambda c: c["symbol"])
    _atomic_write(idx_p, json.dumps(idx, indent=1))


def _atomic_write(path: Path, text: str) -> None:
    """Readers see the old file or the new one, never half of one; writers never share a temp file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)
