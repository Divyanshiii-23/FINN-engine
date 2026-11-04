"""Explanations: what happened, and why it matters.

The default explainer is a template over extracted facts, computed figures and
the materiality components, so every number it prints was computed by code.

An optional LLM explainer can rephrase the same inputs. Its output is accepted
only if it parses, stays short, and every number in it matches a number in the
inputs (numeric grounding). Otherwise the template is used and the rejection
reason is recorded. The LLM never receives the raw filing, only the facts.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable

import requests

from .fmt import cr, pct, pp
from .models import Classification, Explanation, Facts, Materiality, ResultsExtraction
from .materiality import CATEGORY_LABEL

_PREFIX = re.compile(r"^.*?\s-\s\d{6}\s-\s")


def _clean(s: str, n: int = 170) -> str:
    s = _PREFIX.sub("", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def what_happened(cls: Classification, facts: Facts, results: ResultsExtraction | None, subject: str, headline: str | None, is_financial: bool) -> str:
    c, s = cls.category, cls.subtype
    if c == "results" and s in {"financial_results", "board_meeting_outcome"} and results is not None:
        if results.status in {"ok", "needs_review"} and results.rows:
            rows = {r.key: r for r in results.rows}
            rev, pat = rows.get("revenue"), rows.get("pat")
            label = results.period_label or "Quarterly"
            parts = []
            if rev and rev.current.value is not None:
                parts.append(f"revenue ₹{cr(rev.current.value)} cr ({pct(rev.yoy)} YoY)")
            if pat and pat.current.value is not None:
                parts.append(f"PAT ₹{cr(pat.current.value)} cr ({pct(pat.yoy)} YoY)")
            text = f"{label} results: " + ", ".join(parts) + "."
            if results.margin and results.margin.get("current") is not None and results.margin.get("prev_y") is not None and not is_financial:
                d = (results.margin["current"] - results.margin["prev_y"]) * 100
                text += f" EBITDA margin {pct(results.margin['current'], signed=False)} ({pp(d)} YoY)."
            if results.status == "needs_review":
                text += " Figures flagged for review."
            return text
        return f"Results filed; figures could not be extracted ({results.reason})."
    if c == "credit_rating" and facts.rating_action:
        move = f" from {facts.rating_from} to {facts.rating_to}" if facts.rating_from and facts.rating_to else ""
        return f"Credit rating {facts.rating_action}{move}."
    if c == "management_change" and len(facts.changes) > 1:
        parts = [f"{ch['action']}: {', '.join(x for x in [ch.get('person'), ch.get('role')] if x)}" for ch in facts.changes]
        return "; ".join(p[0].upper() + p[1:] for p in parts) + "."
    if c == "management_change" and (facts.person or facts.role):
        who = ", ".join(x for x in [facts.person, facts.role] if x)
        action = (facts.person_action or s or "change").replace("_", " ")
        return f"{action.capitalize()}: {who}."
    if c == "pledging" and facts.pledge_pct is not None:
        prev = f" (previously {facts.pledge_prev_pct}%)" if facts.pledge_prev_pct is not None else ""
        return f"Promoter pledge {(s or 'update').replace('_', ' ')}: {facts.pledge_pct}% of promoter holding{prev}."
    if c == "dividend" and facts.dividend_per_share is not None:
        rd = f", record date {facts.record_date}" if facts.record_date else ""
        return f"Dividend of ₹{facts.dividend_per_share:g} per share{rd}."
    # Otherwise: the filing's own words.
    return _clean(headline or subject)


def why_it_matters(m: Materiality, cls: Classification) -> str:
    if m.floor:
        lead = m.floor + "."
    elif cls.routine:
        return "Routine compliance paperwork; no action needed."
    else:
        lead = ""
    if cls.method == "fallback":
        return "Not matched to a known filing type; shown for review."
    drivers = sorted((c for c in m.components if c.code not in {"type", "floor", "routine_cap"} and c.points > 0), key=lambda c: -c.points)
    if not drivers and not lead:
        # Nothing moved the score: state the starting point and what was checked.
        checked = [c.detail for c in m.components if c.code in {"results_pat", "results_margin", "results", "size", "reaction", "pledge"}]
        kind = (cls.subtype or cls.category).replace("_", " ")
        base = f"{kind.capitalize()} filings start at {m.components[0].points:g}"
        soft = lambda d: d[0].lower() + d[1:] if len(d) > 1 and d[1].islower() else d  # noqa: E731  keep "PAT", "EBITDA"
        return base + ("; " + "; ".join(soft(d) for d in checked[:2]) if checked else "") + "."
    detail = "; ".join(c.detail for c in drivers[:2])
    if detail:
        detail = detail[0].upper() + detail[1:] + "."
    if lead and detail:
        return f"{lead} {detail}"
    if lead or detail:
        return lead or detail
    if cls.method == "fallback":
        return "Not matched to a known filing type; shown for review."
    kind = (cls.subtype or cls.category).replace("_", " ")
    return f"{kind.capitalize()} filings start at {m.components[0].points:g}; no size, results or market signal was available to move that."


def template(cls: Classification, facts: Facts, results: ResultsExtraction | None, m: Materiality, subject: str, headline: str | None, is_financial: bool) -> Explanation:
    return Explanation(what=what_happened(cls, facts, results, subject, headline, is_financial), why=why_it_matters(m, cls), generator="template", grounded=True)


# ---------------------------------------------------------------- LLM path

_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    out = set()
    for t in _NUM.findall(text):
        try:
            out.add(round(float(t.replace(",", "")), 1))
        except ValueError:
            pass
    return out


# Words that add a cause, a judgement or a forecast. A rewording may use them only if the
# inputs already do; otherwise "margins fell due to pricing pressure" could slip through a
# check that only compares numbers.
_CAUSAL = re.compile(r"\b(because|due to|driven by|owing to|as a result|thanks to|led by|on the back of|amid|caused|reflect(s|ing|ed)?|attribut\w*|since)\b", re.I)
_JUDGEMENT = {"strong", "stronger", "weak", "weaker", "robust", "impressive", "concerning", "worrying", "healthy", "solid", "poor", "excellent",
              "disappointing", "significant", "significantly", "sharp", "sharply", "dramatic", "dramatically", "likely", "unlikely", "expected",
              "will", "should", "risk", "risky", "positive", "negative", "bullish", "bearish", "buy", "sell", "undervalued", "overvalued"}
_STOP = {"this", "that", "with", "from", "were", "than", "have", "been", "which", "their", "there", "they", "into", "about", "over", "also",
         "only", "what", "when", "where", "while", "more", "less", "same", "each", "both", "such", "against", "after", "before", "under",
         # neutral connective and movement words a plain rewording needs
         "fell", "fall", "falls", "rose", "rise", "rises", "down", "lower", "higher", "increase", "increased", "decrease", "decreased",
         "compared", "versus", "quarter", "year", "period", "change", "changed", "moved", "figure", "reported", "company", "previous", "prior"}
_WORD = re.compile(r"[a-z]+")


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _WORD.findall(text.lower()) if len(w) > 3}


def grounded(candidate: str, allowed_text: str, min_share: float = 0.6) -> tuple[bool, str | None]:
    """A model's wording is kept only if it adds nothing: no new numbers, no causes or
    judgements the inputs don't contain, no capitalised names, and most content words traceable."""
    allowed = _numbers(allowed_text)
    stray = [n for n in _numbers(candidate) if n not in allowed and abs(n) not in allowed]
    if stray:
        return False, f"numbers not in the inputs: {stray[:5]}"
    low_allowed = allowed_text.lower()
    for m in _CAUSAL.finditer(candidate):
        if m.group(0).lower() not in low_allowed:
            return False, f"adds a causal claim: {m.group(0)!r}"
    words = _WORD.findall(candidate.lower())
    judged = [w for w in words if w in _JUDGEMENT and not re.search(rf"\b{w}\b", low_allowed)]
    if judged:
        return False, f"adds a judgement: {judged[:3]}"
    names = [t for t in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z&]{2,}\b", candidate.strip()) if t.lower() not in low_allowed]
    if names:
        return False, f"names not in the inputs: {names[:3]}"
    content = [w for w in words if len(w) > 3 and w not in _STOP]
    if content:
        st = _stems(allowed_text)
        share = sum(w[:5] in st for w in content) / len(content)
        if share < min_share:
            return False, f"only {share:.0%} of its words trace to the inputs"
    return True, None


def llm_explain(base: Explanation, inputs: dict, complete: Callable[[str], str], model: str) -> Explanation:
    """Rephrase the template using an LLM; keep the template unless the output is grounded."""
    allowed_text = json.dumps(inputs, default=str) + " " + base.what + " " + base.why
    prompt = (
        "You write two short sentences for an investor about one exchange filing.\n"
        "Use ONLY the facts below. Do not add numbers, names or causes that are not in them.\n"
        'Reply as JSON: {"what": "<what happened, max 25 words>", "why": "<why it matters, max 25 words>"}\n'
        f"FACTS: {json.dumps(inputs, default=str)}\n"
        f"DRAFT: what={base.what!r} why={base.why!r}"
    )
    try:
        raw = complete(prompt)
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        what, why = str(data["what"]).strip(), str(data["why"]).strip()
    except Exception as e:  # noqa: BLE001
        return base.model_copy(update={"rejected_llm_reason": f"unparseable LLM output: {type(e).__name__}"})
    if len(what) > 220 or len(why) > 220 or not what or not why:
        return base.model_copy(update={"rejected_llm_reason": "LLM output too long or empty"})
    ok, reason = grounded(what + " " + why, allowed_text)
    if not ok:
        return base.model_copy(update={"rejected_llm_reason": reason})
    return Explanation(what=what, why=why, generator=f"llm:{model}", grounded=True)


def gemini_completer() -> tuple[Callable[[str], str], str] | None:
    """Enabled only when GEMINI_API_KEY and FINN_EXPLAIN_MODEL are both set."""
    key, model = os.environ.get("GEMINI_API_KEY"), os.environ.get("FINN_EXPLAIN_MODEL")
    if not key or not model:
        return None

    def complete(prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = requests.post(
            url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    return complete, model
