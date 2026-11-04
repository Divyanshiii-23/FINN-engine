"""Earnings-call transcripts: roster, speaker turns, roles and sections.

Formats differ by company and by transcription vendor, so the parser looks
for a few stable cues rather than one layout:

* a participants block naming management with titles;
* speaker labels at the start of a line: "Name:", "Name - Title:", "Moderator:";
* the moderator's first-question cue, which starts the Q&A section.

When no labels are found, turns fall back to page windows with role
"unknown"; claims from them are flagged speaker_unverified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdftext import PdfText

LABEL = re.compile(r"^((?:Mr\.|Ms\.|Mrs\.|Dr\.)?\s?[A-Z][A-Za-z.'`]+(?:\s[A-Z][A-Za-z.'`]+){0,4})(?:\s?[-,]\s?([A-Za-z &/,.]{2,60}?))?\s?:\s?(.*)$")
MODERATOR = re.compile(r"^(moderator|operator|coordinator)$", re.I)
MGMT_TITLES = re.compile(r"\b(managing director|md|ceo|cfo|chief|chairman|chairperson|whole[- ]time director|executive director|president|head|vice president|vp|director|company secretary|investor relations|founder|group cfo|joint managing director|coo|cto)\b", re.I)
QA_CUE = re.compile(r"(first question|question[- ]and[- ]answer|q\s?&\s?a session|begin the question|open the floor|we will now begin|we have the first)", re.I)
ANALYST_INTRO = re.compile(r"(?:question|line) (?:is )?from (?:the line of )?((?:Mr\.|Ms\.)?\s?[A-Z][A-Za-z.]+(?:\s[A-Z][A-Za-z.]+){0,3})\s+(?:from|of|with)\s+([A-Z][\w&.\- ]+)")
SAFE_HARBOUR = re.compile(r"(forward[- ]looking statements|safe harbou?r|actual results may differ|risks and uncertainties)", re.I)


@dataclass
class Turn:
    idx: int
    speaker: str
    role: str  # management | analyst | moderator | unknown
    title: str | None
    section: str  # Prepared remarks | Q&A
    page_start: int
    page_end: int
    text: str
    lines: list[tuple[int, str]] = field(default_factory=list)  # (page, text)


@dataclass
class Transcript:
    turns: list[Turn]
    roster: dict[str, str]  # normalised name -> title
    labelled: bool
    notes: list[str] = field(default_factory=list)


def _key(name: str) -> str:
    n = re.sub(r"^(mr|ms|mrs|dr)\.?\s+", "", name.strip(), flags=re.I).lower()
    return re.sub(r"[^a-z ]", "", n).strip()


def _roster(lines: list[tuple[int, str]]) -> dict[str, str]:
    """Management names and titles from the participants block on the first pages."""
    out: dict[str, str] = {}
    in_block = False
    for page, t in lines:
        if page > 3:
            break
        low = t.lower()
        if re.match(r"^(management|participants|company participants|management participants|on the call)\b", low):
            in_block = True
            continue
        if in_block and re.match(r"^(moderator|analysts?|operator)\b", low) and ":" in t[:20]:
            in_block = False
        m = re.match(r"^((?:Mr\.|Ms\.|Mrs\.|Dr\.)\s?[A-Z][A-Za-z.]+(?:\s[A-Z][A-Za-z.]+){0,3})\s?[-,–:]\s?(.+)$", t)
        if m and MGMT_TITLES.search(m.group(2)) and (in_block or page == 1):
            out[_key(m.group(1))] = m.group(2).strip(" .")
    return out


def parse(pdf: PdfText) -> Transcript:
    lines = [(l.page, l.text) for l in pdf.lines]
    roster = _roster(lines)
    analysts: set[str] = set()
    turns: list[Turn] = []
    section = "Prepared remarks"
    cur: Turn | None = None
    started = False
    for page, t in lines:
        m = LABEL.match(t)
        is_label = bool(m) and len(m.group(1)) <= 40 and not re.match(r"^(note|disclaimer|safe harbour|date|time|page|ref|subject|sub|dear|management|participants|company participants|analysts|speakers|present|on the call)\b", m.group(1), re.I) if m else False
        if is_label:
            name = m.group(1).strip()  # type: ignore[union-attr]
            title = (m.group(2) or "").strip() or None  # type: ignore[union-attr]
            body = (m.group(3) or "").strip()  # type: ignore[union-attr]
            k = _key(name)
            if MODERATOR.match(name):
                role = "moderator"
            elif k in roster or (title and MGMT_TITLES.search(title)) or any(k.split()[-1:] == r.split()[-1:] and k[:1] == r[:1] for r in roster):
                role = "management"
                if title and k not in roster:
                    roster[k] = title
            elif k in analysts:
                role = "analyst"
            else:
                role = "analyst" if started and section == "Q&A" else "unknown"
            started = True
            if role == "moderator" and QA_CUE.search(body):
                section = "Q&A"
            cur = Turn(idx=len(turns), speaker=name, role=role, title=roster.get(k, title), section=section, page_start=page, page_end=page, text=body, lines=[(page, body)] if body else [])
            turns.append(cur)
            if role == "moderator":
                for am in ANALYST_INTRO.finditer(body):
                    analysts.add(_key(am.group(1)))
            continue
        if cur is None:
            continue
        cur.text = (cur.text + " " + t).strip()
        cur.lines.append((page, t))
        cur.page_end = page
        if cur.role == "moderator":
            if QA_CUE.search(t):
                section = "Q&A"
            for am in ANALYST_INTRO.finditer(cur.text):
                analysts.add(_key(am.group(1)))
    # Second pass: speakers first seen before they were introduced.
    for tr in turns:
        if tr.role == "unknown" and _key(tr.speaker) in analysts:
            tr.role = "analyst"
    labelled = sum(1 for t in turns if t.role in ("management", "analyst", "moderator")) >= 3
    notes: list[str] = []
    if not labelled:
        notes.append("No speaker labels found; text is read page by page and claims are marked speaker unverified.")
        turns = []
        for p in range(1, pdf.pages + 1):
            body = pdf.page_text(p)
            if body.strip():
                turns.append(Turn(idx=len(turns), speaker="Unknown", role="unknown", title=None, section="Unknown", page_start=p, page_end=p, text=body.replace("\n", " "), lines=[(p, x) for x in body.split("\n")]))
    if not roster:
        notes.append("No participants block found; management identified from titles in speaker labels.")
    return Transcript(turns=turns, roster=roster, labelled=labelled, notes=notes)


def is_boilerplate(sentence: str) -> bool:
    return bool(SAFE_HARBOUR.search(sentence))
