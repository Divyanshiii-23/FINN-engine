"""The narrative path: documents → turns/sentences → gated claims.

Transcripts are read turn by turn so every claim keeps its speaker, role,
section and page. Presentations and annual reports are company documents,
so their text is attributed to the company rather than a person.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from . import claims as C
from . import transcript as T
from .models import Claim, Doc
from .pdftext import PdfText, norm, sentences

DATE_TEXT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s(january|february|march|april|may|june|july|august|september|october|november|december),?\s(20\d{2})\b|\b(january|february|march|april|may|june|july|august|september|october|november|december)\s(\d{1,2}),?\s(20\d{2})\b", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], start=1)}


def call_date(pdf: PdfText, doc: Doc) -> date:
    """The call date printed on the first page, else the filing date."""
    first = " ".join(l.text for l in pdf.lines if l.page == 1)[:2500]
    m = DATE_TEXT.search(first)
    if m:
        if m.group(1):
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        return date(int(m.group(6)), MONTHS[m.group(4).lower()], int(m.group(5)))
    return (doc.filed_at or datetime.now()).date()


def _sentences_with_pages(lines: list[tuple[int, str]]) -> list[tuple[str, int]]:
    text, starts = "", []
    for page, t in lines:
        starts.append((len(text), page))
        text += t + " "
    out: list[tuple[str, int]] = []
    pos = 0
    for s in sentences(text):
        i = text.find(s, pos)
        i = i if i >= 0 else pos
        page = next((p for st, p in reversed(starts) if st <= i), starts[0][1] if starts else 1)
        out.append((s, page))
        pos = i + len(s)
    return out


def _dedupe(cs: list[Claim]) -> list[Claim]:
    """Same (metric, segment, period, target) within one document: keep the first."""
    seen: dict[tuple, Claim] = {}
    out: list[Claim] = []
    for c in cs:
        if c.kind == "outlook":
            key = ("outlook", c.quote)
        else:
            t = c.target
            key = (c.kind, c.metric, c.segment, c.period, t.kind if t else None, t.low if t else None, t.high if t else None, c.reaffirms, c.withdraws, c.basis_hint)
        if key in seen:
            continue
        seen[key] = c
        out.append(c)
    return out


def from_transcript(doc: Doc, pdf: PdfText, ctx: dict) -> tuple[list[Claim], dict]:
    tr = T.parse(pdf)
    cdate = call_date(pdf, doc)
    pages = {p: pdf.page_text(p) for p in range(1, pdf.pages + 1)}
    out: list[Claim] = []
    rejected = 0
    question: str | None = None
    for turn in tr.turns:
        if turn.role == "analyst":
            question = turn.text
            continue
        if turn.role == "moderator":
            continue
        prev = None
        for s, page in _sentences_with_pages(turn.lines):
            if T.is_boilerplate(s):
                prev = s
                continue
            for c in C.classify(s, doc_id=doc.id, doc_kind="transcript", call_period=doc.period, call_date=cdate, page=page, section=turn.section,
                                speaker=turn.speaker + (f", {turn.title}" if turn.title else ""), role=turn.role if turn.role != "unknown" else "unknown",
                                prev_sentence=prev, question=question if turn.section == "Q&A" else None, threads=ctx["threads"],
                                is_financial=ctx["is_financial"], is_it=ctx["is_it"], segments=ctx["segments"]):
                c = C.accept(C.gates(c, pages, turn.text))
                if c is None:
                    rejected += 1
                    continue
                if c.role == "unknown":
                    c.gates["speaker_unverified"] = True
                out.append(c)
                if c.kind == "guidance" and c.metric:
                    ctx["threads"].add(f"{c.metric}|{c.period}")
            prev = s
    info = {
        "turns": len(tr.turns),
        "management_turns": sum(1 for t in tr.turns if t.role == "management"),
        "analyst_turns": sum(1 for t in tr.turns if t.role == "analyst"),
        "roster": tr.roster,
        "labelled": tr.labelled,
        "call_date": cdate.isoformat(),
        "claims_rejected_by_gates": rejected,
        "notes": tr.notes,
        "complete": tr.labelled,
    }
    return _dedupe(out), info


AR_SECTIONS = re.compile(r"^(management discussion and analysis|management's discussion|outlook|business outlook|the year ahead|way forward|future outlook)\b", re.I)


def from_document(doc: Doc, pdf: PdfText, ctx: dict) -> tuple[list[Claim], dict]:
    """Presentations (bullets) and annual reports (MD&A paragraphs)."""
    pages = {p: pdf.page_text(p) for p in range(1, pdf.pages + 1)}
    out: list[Claim] = []
    rejected = 0
    when = (doc.filed_at or datetime.now()).date()
    for p in range(1, pdf.pages + 1):
        lines = [l.text for l in pdf.lines if l.page == p]
        if not lines:
            continue
        title = lines[0]
        if doc.kind == "annual_report" and not any(AR_SECTIONS.match(t) for t in lines[:3]):
            continue  # only MD&A / outlook pages carry forward-looking statements worth reading
        if doc.kind == "presentation":
            items = [(t, p) for t in lines[1:] if len(t) > 15]
        else:
            items = _sentences_with_pages([(p, t) for t in lines[1:]])
        prev = None
        for s, page in items:
            for c in C.classify(s, doc_id=doc.id, doc_kind=doc.kind, call_period=doc.period, call_date=when, page=page, section=title,
                                speaker="Company document", role="company", prev_sentence=prev, question=None, threads=ctx["threads"],
                                is_financial=ctx["is_financial"], is_it=ctx["is_it"], segments=ctx["segments"]):
                c = C.accept(C.gates(c, pages, " ".join(lines)))
                if c is None:
                    rejected += 1
                    continue
                out.append(c)
                if c.kind == "guidance" and c.metric:
                    ctx["threads"].add(f"{c.metric}|{c.period}")
            prev = s
    return _dedupe(out), {"claims_rejected_by_gates": rejected, "complete": True}


OVERVIEW = re.compile(r"^(company overview|corporate overview|about (us|the company)|who we are|business overview|our business|at a glance|company at a glance|corporate snapshot)\b", re.I)


def business_overview(doc: Doc, pdf: PdfText) -> tuple[str, int, str] | None:
    """First substantive paragraph under an overview heading: (text, page, heading)."""
    for p in range(1, pdf.pages + 1):
        lines = [l.text for l in pdf.lines if l.page == p]
        for i, t in enumerate(lines):
            if OVERVIEW.match(t):
                body = " ".join(lines[i + 1:i + 8])
                ss = [s for s in sentences(body) if len(s) > 40][:3]
                if ss:
                    return norm(" ".join(ss)), p, t
    return None
