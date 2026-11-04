"""Deterministic fact extraction from filing text (subject, headline, and the
first page of the attachment when it was downloaded).

Only values that literally appear in the text are extracted. Anything not
found stays None, and the materiality and explanation steps say so.
"""

from __future__ import annotations

import re

from ..models import Facts

_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|millions?|mn|billions?|bn)\b"
    r"|([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?)\b",
    re.I,
)
_COUNT_AFTER = re.compile(r"\s*(equity\s+)?(shares|units|warrants|options|securities)\b", re.I)
_SHARES_AT = re.compile(r"([\d,]+(?:\.\d+)?)\s*(crores?|lakhs?)\s+(?:equity\s+)?shares?\b.{0,40}?(?:at|@)\s*(?:a price of\s*)?(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:/-\s*)?per", re.I)
_FACTOR = {"crore": 1.0, "cr": 1.0, "lakh": 0.01, "lac": 0.01, "million": 0.1, "mn": 0.1, "billion": 100.0, "bn": 100.0}
_RATING = r"[A-D]{1,3}[+\-−]?(?:\s*\((?:SO|CE)\))?"
_RATING_MOVE = re.compile(rf"from\s+['\"‘“]?({_RATING})['\"’”]?\s*(?:\([^)]*\))?\s+to\s+['\"‘“]?({_RATING})", re.I)
_PERSON = re.compile(r"\b(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?)\s+([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+){0,3})")
_ROLE = re.compile(
    r"\b(chief financial officer|cfo|chief executive officer|ceo|managing director|whole[- ]time director|"
    r"executive director|independent director|non-executive director|company secretary|compliance officer|"
    r"statutory auditors?|chairman|chairperson|chief operating officer|coo|director)\b",
    re.I,
)
_ROLE_CANON = {"cfo": "Chief Financial Officer", "ceo": "Chief Executive Officer", "coo": "Chief Operating Officer"}
_ACTION = [
    ("resignation", re.compile(r"resign", re.I)),
    ("cessation", re.compile(r"cessation|ceases?", re.I)),
    ("retirement", re.compile(r"retire", re.I)),
    ("reappointment", re.compile(r"re-?appoint", re.I)),
    ("appointment", re.compile(r"appoint", re.I)),
]
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_DPS = re.compile(r"(?:₹|rs\.?|inr)\s*([\d.]+)\s*(?:/-\s*)?per\s*(?:equity\s*)?share", re.I)
_RECORD = re.compile(r"record date\s*(?:is|of|:|-)?\s*(?:fixed as|being)?\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4})", re.I)


def amounts_cr(text: str) -> tuple[list[float], str | None]:
    out: list[float] = []
    first: str | None = None
    for m in _AMOUNT.finditer(text):
        if not m.group(1) and _COUNT_AFTER.match(text, m.end()):
            continue  # "1.2 crore equity shares" is a count of shares, not rupees
        num = m.group(1) or m.group(3)
        unit = (m.group(2) or m.group(4) or "").lower().rstrip("s.")
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        f = next((f for k, f in _FACTOR.items() if unit.startswith(k)), None)
        if f is None:
            continue
        out.append(round(v * f, 2))
        first = first or m.group(0)
    # A share count at a stated price ("1.2 crore equity shares at Rs. 1,500 per share") is a rupee amount.
    for m in _SHARES_AT.finditer(text):
        n = float(m.group(1).replace(",", "")) * (1e7 if m.group(2).lower().startswith("crore") else 1e5)
        out.append(round(n * float(m.group(3).replace(",", "")) / 1e7, 2))
        first = first or m.group(0)
    return out, first


def extract_facts(category: str, subtype: str | None, text: str) -> Facts:
    f = Facts()
    f.amounts_cr, f.amount_text = amounts_cr(text)
    if category == "credit_rating":
        m = _RATING_MOVE.search(text)
        if m:
            f.rating_from, f.rating_to = m.group(1).replace("−", "-"), m.group(2).replace("−", "-")
        f.rating_action = {"downgrade": "downgrade", "upgrade": "upgrade", "reaffirm": "reaffirm", "withdrawn": "withdrawn"}.get(subtype or "")  # type: ignore[assignment]
    if category == "management_change":
        p = _PERSON.search(text)
        if p:
            f.person = p.group(1).strip().rstrip(".")
        r = _ROLE.search(text)
        if r:
            role = r.group(1).lower()
            f.role = _ROLE_CANON.get(role, role.title())
        for name, pat in _ACTION:
            if pat.search(text):
                f.person_action = name  # type: ignore[assignment]
                break
    if category == "pledging":
        pcts = [float(x) for x in _PCT.findall(text)]
        if pcts:
            f.pledge_pct = pcts[0]
            if len(pcts) > 1:
                f.pledge_prev_pct = pcts[1]
    if category == "dividend":
        d = _DPS.search(text)
        if d:
            f.dividend_per_share = float(d.group(1))
    r = _RECORD.search(text)
    if r:
        f.record_date = r.group(1)
    return f
