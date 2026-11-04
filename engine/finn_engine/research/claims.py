"""Management statements → typed claims, with deterministic gates.

Classification follows the AI design doc's rules, first match wins:

1. Not management (analyst, moderator) → not a claim.
2. Management confirms an analyst's figure → classified by 3-4, flagged.
3. About the future:
   metric + number/range/vague quantifier + resolvable period → guidance;
   metric + definite direction + resolvable period → guidance (directional);
   "we maintain our guidance" → guidance that reaffirms an existing thread;
   anything else → commentary (outlook). Never scored.
4. About the past or present with a mappable metric → assertion (checked).
5. Otherwise → commentary only if it names a tracked theme; else dropped.

Targets are parsed from management's own words by code. A phrase with no
rule ("healthy", "strong", "meaningful") yields no target: the claim stays
commentary or directional, and no number is ever derived from it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from . import periods as P
from .metrics import BY_ID, Metric, find
from .models import Claim, Target
from .pdftext import norm, sentences

# ------------------------------------------------------------------ numbers

NUM = r"(?:₹|rs\.?|inr)?\s?\d[\d,]*(?:\.\d+)?"
UNIT_RE = r"(%|percent|per cent|bps|basis points|crores?|cr\b|lakh crores?|bn\b|billion|mn\b|million|x\b|times)"
NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def num(s: str) -> float:
    m = NUM_TOKEN.search(s)
    return float(m.group(0).replace(",", "")) if m else float("nan")


def _scale(unit: str) -> tuple[str, float]:
    u = unit.lower().strip()
    if u in ("%", "percent", "per cent"):
        return "pct", 1.0
    if u in ("bps", "basis points"):
        return "bps", 1.0
    if u.startswith("lakh crore"):
        return "cr", 100000.0
    if u.startswith("cr"):
        return "cr", 1.0
    if u in ("bn", "billion"):
        return "cr", 100.0
    if u in ("mn", "million"):
        return "cr", 0.1
    if u in ("x", "times"):
        return "x", 1.0
    return u, 1.0


# Quantity words with no defined bounds. They are recorded as said, never as numbers.
VAGUE = [
    r"(?:low|mid|high)[- ]single[- ]digits?", r"single[- ]digits?", r"(?:low|mid|high)[- ]teens", r"(?:low|mid|high)[- ]twenties",
    r"\b(?:significant|meaningful|substantial|sizeable|healthy|robust|strong|decent|modest|marginal)\s(?:\w+\s)?(?:growth|improvement|expansion|increase|uptick)",
]
UP = r"improv|expan|increas|ris(e|ing)|higher|better|recover|grow|growth|scale up|step up|accelerat|inch up|uptick"
DOWN = r"declin|moderat|contract|lower|reduc|fall|soften|compress|come down|dip|taper|normali[sz]"
FLAT = r"\b(stable|steady|flat|maintain(ed)? at|sustain(ed)? at|similar levels|in line with last year)\b"


def parse_target(clause: str, metric: Metric) -> Target | None:
    """Target from the clause's own words. Returns None rather than guess."""
    low = clause.lower()
    # Foreign-currency amounts ("USD 410 million") are blanked so they're never read as rupees.
    low = re.sub(r"(?:usd|us\$|\$|eur|€|gbp|£)\s?\d[\d,.]*\s?(?:million|mn|billion|bn)?", lambda m: " " * len(m.group(0)), low)
    unit_ok = {"growth": {"pct"}, "level": {"pct", "bps"}, "amount": {"cr"}, "days": {"days", ""}, "ratio": {"x"}}[metric.kind]

    def tgt(kind, lo, hi, unit, text, reading, **kw) -> Target:
        return Target(kind=kind, low=lo, high=hi, unit=unit, text=text, reading=reading, **kw)

    # delta in bps / pp
    m = re.search(rf"({NUM})\s?(?:-|to)\s?({NUM})\s?(bps|basis points)|({NUM})\s?(bps|basis points)", low)
    if m and metric.kind == "level" and re.search(UP + "|" + DOWN, low):
        lo, hi = (num(m.group(1)), num(m.group(2))) if m.group(1) else (num(m.group(4)), num(m.group(4)))
        sign = -1 if re.search(DOWN, low) and not re.search(UP, low) else 1
        base = re.search(r"(?:over|from|versus|vs\.?|compared to)\s(?:the\s)?(fy\s?'?\d{2}|last year|previous year|last fiscal)", low)
        bp = None
        if base:
            mm = re.search(r"\d{2}", base.group(1))
            bp = f"FY{mm.group(0)}" if mm else "last full year"
        text = clause[m.start():m.end()].strip()
        lo_pp, hi_pp = sorted((sign * lo / 100, sign * hi / 100))
        return tgt("delta", lo_pp, hi_pp, "pp", text, f"'{text}' read as {lo_pp:+.2f} to {hi_pp:+.2f} pp" + (f" against {bp}" if bp else " against the last full year"), base_period=bp)

    # "23% plus or minus 50 basis points"
    m = re.search(rf"({NUM})\s?%\s?(?:plus or minus|\+/-|±|\+-)\s?({NUM})\s?(bps|basis points|%)", low)
    if m and "pct" in unit_ok:
        c, w = num(m.group(1)), num(m.group(2)) / (100 if m.group(3) != "%" else 1)
        text = clause[m.start():m.end()].strip()
        return tgt("range", round(c - w, 4), round(c + w, 4), "pct", text, f"'{text}' read as {c - w:g} to {c + w:g}%")

    # range a-b unit
    for m in re.finditer(rf"({NUM})\s?{UNIT_RE}?\s?(?:-|to)\s?({NUM})\s?{UNIT_RE}", low):
        u, f = _scale(m.group(4))
        if u in unit_ok and (not m.group(2) or _scale(m.group(2))[0] == u):
            lo, hi = num(m.group(1)) * f, num(m.group(3)) * f
            text = clause[m.start():m.end()].strip()
            return tgt("range", min(lo, hi), max(lo, hi), u, text, f"'{text}' read as {min(lo, hi):g} to {max(lo, hi):g}{'%' if u == 'pct' else ' ' + u}")

    for pat in VAGUE:
        m = re.search(pat, low)
        if m and metric.kind in ("growth", "level"):
            text = clause[m.start():m.end()].strip()
            return tgt("words", None, None, None, text,
                       f"No number stated: '{text}' is kept in management's words. FINN doesn't turn it into a range, so this isn't scored.")
    m = re.search(r"double[- ]digits?", low)
    if m and metric.kind in ("growth", "level"):
        text = clause[m.start():m.end()].strip()
        return tgt("floor", 10, None, "pct", text, f"'{text}' read literally as 10% or more (the smallest two-digit number)")
    m = re.search(r"\b(double|doubling|triple|tripling)\b", low)
    if m and metric.kind in ("growth", "amount"):
        x = 2.0 if m.group(1).startswith("doubl") else 3.0
        text = clause[m.start():m.end()].strip()
        return tgt("multiple", x, x, "x", text, f"'{text}' read as {x:g}x the last full year before the statement")

    for m in re.finditer(rf"(at least|minimum of|minimum|in excess of|more than|upwards of|north of|not less than|over|above)\s({NUM})\s?{UNIT_RE}", low):
        u, f = _scale(m.group(3))
        if u in unit_ok:
            v = num(m.group(2)) * f
            text = clause[m.start():m.end()].strip()
            return tgt("floor", v, None, u, text, f"'{text}' read as {v:g}{'%' if u == 'pct' else ' ' + u} or more")
    for m in re.finditer(rf"(up to|not more than|maximum of|below|under|less than|within)\s({NUM})\s?{UNIT_RE}", low):
        u, f = _scale(m.group(3))
        if u in unit_ok:
            v = num(m.group(2)) * f
            text = clause[m.start():m.end()].strip()
            return tgt("ceiling", None, v, u, text, f"'{text}' read as {v:g}{'%' if u == 'pct' else ' ' + u} or less")
    for m in re.finditer(rf"(around|about|approximately|approx\.?|~|close to|nearly|roughly|in the region of)\s?({NUM})\s?{UNIT_RE}", low):
        u, f = _scale(m.group(3))
        if u in unit_ok:
            v = num(m.group(2)) * f
            text = clause[m.start():m.end()].strip()
            if u == "pct":
                return tgt("point", v - 1, v + 1, u, text, f"'{text}' read as {v - 1:g} to {v + 1:g}% (approximate: ±1 pp)")
            return tgt("point", round(v * 0.95, 2), round(v * 1.05, 2), u, text, f"'{text}' read as {v:g} {u} ±5%")
    for m in re.finditer(rf"({NUM})\s?{UNIT_RE}", low):
        u, f = _scale(m.group(2))
        if u in unit_ok:
            v = num(m.group(1)) * f
            text = clause[m.start():m.end()].strip()
            return tgt("point", v, v, u, text, f"'{text}' read as {v:g}{'%' if u == 'pct' else ' ' + u}")
    return None


def direction(clause: str) -> str | None:
    low = clause.lower()
    if re.search(FLAT, low):
        return "flat"
    up, down = re.search(UP, low), re.search(DOWN, low)
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    return None


# ------------------------------------------------------------------ periods

def resolve_period(text: str, call_date: date, call_period: str | None, past: bool = False) -> tuple[str | None, str | None, bool]:
    """(period label, matched text, is_horizon). Unresolvable → (None, None, False)."""
    low = text.lower()
    cur = P.fy_of(call_date)
    rep = P.parse(call_period) if call_period else None
    m = re.search(r"\b(q[1-4])\s?(?:of\s)?fy\s?'?(\d{2,4})\b", low)
    if m:
        return f"{m.group(1).upper()} FY{m.group(2)[-2:]}", m.group(0), False
    m = re.search(r"\b(h[12]|first half|second half)\s?(?:of\s)?(?:fy\s?'?(\d{2,4}))?", low)
    if m:
        h = "H1" if m.group(1) in ("h1", "first half") else "H2"
        fy = int(m.group(2)[-2:]) + 2000 if m.group(2) else (rep[1] if past and rep else cur)
        return f"{h} FY{fy % 100:02d}", m.group(0), False
    m = re.search(r"\bfy\s?'?(20)?(\d{2})\b|\b20(\d{2})\s?-\s?(?:20)?(\d{2})\b|financial year 20(\d{2})", low)
    if m:
        yy = m.group(2) or m.group(4) or m.group(5)
        return f"FY{yy}", m.group(0), False
    m = re.search(r"\b(?:by|until|till|before|in|as of|at the end of|end of)\s(?:the end of\s)?(march|mar|june|jun|september|sept|sep|december|dec)\s?'?(20\d{2}|\d{2})\b", low)
    if m:
        mo = {"mar": 3, "jun": 6, "sep": 9, "dec": 12}[m.group(1)[:3]]
        yr = int(m.group(2)) if len(m.group(2)) == 4 else 2000 + int(m.group(2))
        lab = P.label_for_end(date(yr, mo, {3: 31, 6: 30, 9: 30, 12: 31}[mo]), "ytd")
        if lab:
            return lab, m.group(0), False
    m = re.search(r"next (two|three|four|five|2|3|4|5)(?: to (?:three|four|five|six|3|4|5|6))? years|in (?:the next )?(three|four|five|3|4|5) years|over the medium term|medium[- ]term", low)
    if m:
        words = {"two": 2, "three": 3, "four": 4, "five": 5, "2": 2, "3": 3, "4": 4, "5": 5}
        n = words.get(m.group(1) or m.group(2) or "", 3)
        return f"FY{(cur + n - 1) % 100:02d}", m.group(0), True
    m = re.search(r"\b(this|current|the current|this financial|the full) (year|fiscal|financial year)\b|\bfull[- ]year\b|\bfor the year\b", low)
    if m:
        if past and rep:
            return (f"FY{rep[1] % 100:02d}" if rep[0] == "Q4" else None), m.group(0), False
        return f"FY{cur % 100:02d}", m.group(0), False
    m = re.search(r"\bnext (year|fiscal|financial year)\b", low)
    if m:
        return f"FY{(cur + 1) % 100:02d}", m.group(0), False
    m = re.search(r"\b(next|coming) quarter\b", low)
    if m and call_period:
        return P.prev_q(call_period, -1), m.group(0), False
    m = re.search(r"\bby (q4|the end of the year|year[- ]end)|\bexit(ing)? (rate|the year)", low)
    if m:
        return f"Q4 FY{cur % 100:02d}", m.group(0), False
    if past and call_period and re.search(r"\b(this|the) quarter\b|during the quarter|in the quarter|year[- ]on[- ]year|\byoy\b|sequential|quarter[- ]on[- ]quarter|\bqoq\b", low):
        return call_period, None, False
    return None, None, False


# ------------------------------------------------------------------ cues

FUTURE = re.compile(r"\b(will|shall|expect|expects|expected|expecting|guid(e|ed|ance|ing)|target(ing|ed)?|aim(ing)?|aspir\w*|plan(s|ning)?|should|anticipate|likely to|going to|outlook|project(ing|ed)?|envisage|intend|look to|looking at|confident of|on track|remain comfortable|maintain(ing)? our|reiterat\w*|forecast|budget(ed)?|would be|hope to|endeavou?r)\b", re.I)
PAST = re.compile(r"\b(grew|was|were|reported|delivered|achieved|registered|stood at|came in|declined|improved|expanded|increased|decreased|fell|rose|witnessed|saw|had|has been|have been|remained|was up|was down|is up|is down|are up|are down)\b", re.I)
REAFFIRM = re.compile(r"\b(maintain|reiterate|reaffirm|retain|stick to|remain comfortable with|comfortable with|stand by|on track (for|to achieve|to deliver)|continue to guide)\b.{0,40}\b(guidance|target|outlook|number|range|band)", re.I)
WITHDRAW = re.compile(r"\b(not|no longer|won't|will not|do not|don't|discontinu\w*|withdraw\w*|stop)\b.{0,25}\b(giv\w*|provid\w*|offer\w*|guid\w*)?.{0,25}\bguidance\b", re.I)
CONFIRM = re.compile(r"^(yes|yeah|right|correct|that'?s (right|correct|fair|about right|broadly right)|broadly|absolutely|that is (right|correct))\b", re.I)
NOT_COMPANY = re.compile(r"\b(industry|market|sector|economy|gdp|country|peers|competitors|global demand|the segment as a whole)\b", re.I)
COMPANY = re.compile(r"\b(we|our|us|the company|company's)\b", re.I)
YOY = re.compile(r"year[- ]on[- ]year|\byoy\b|over last year|over the same (period|quarter) last year|versus last year|y-o-y", re.I)
QOQ = re.compile(r"sequential|quarter[- ]on[- ]quarter|\bqoq\b|over the previous quarter|over last quarter|q-o-q", re.I)

HEDGES = [
    ("conditional", re.compile(r"\bif\b|subject to|provided (that)?|assuming|barring|depending on", re.I)),
    ("aspirational", re.compile(r"\baim\w*|aspir\w*|ambition|endeavou?r|hope|would like to|dream", re.I)),
    ("expected", re.compile(r"expect\w*|should|anticipat\w*|likely|estimat\w*|believe|envisage|projected|see\b", re.I)),
    ("firm", re.compile(r"\bwill\b|guid\w*|target\w*|commit\w*|on track|confident of", re.I)),
]

THEMES: list[tuple[str, str]] = [
    ("Demand", r"\bdemand\b|offtake|consumption|end[- ]market"),
    ("Pricing", r"pricing|price (hike|increase|cut)s?|realisations?|realizations?"),
    ("Input costs", r"raw material|input cost|commodit|crude|palm oil|\binflation"),
    ("Margins", r"\bmargins?\b"),
    ("Exports", r"\bexports?\b|overseas|international"),
    ("Capacity and capex", r"\bcapex\b|capacity|expansion|greenfield|brownfield|new plant"),
    ("Debt", r"\bdebt\b|leverage|borrowing"),
    ("Cash generation", r"cash (generation|flow|conversion)|free cash|cash generat|generat\w* cash"),
    ("Working capital", r"working capital|receivable|inventor(y|ies)"),
    ("Deal pipeline", r"pipeline|deal (wins?|flow)|order book|\btcv\b"),
    ("Client spending", r"discretionary|client spend|budgets?|deferr|decision[- ]making"),
    ("People", r"attrition|hiring|headcount|wage|freshers"),
    ("Asset quality", r"asset quality|\bnpa\b|stage[- ]?[23]|delinquen|collection|stress|write[- ]offs?|credit cost"),
    ("Funding", r"cost of funds|funding|liquidity"),
    ("Competition", r"competiti"),
    ("Regulation", r"regulat|usfda|warning letter|compliance"),
]
POSITIVE = re.compile(r"\b(strong|robust|healthy|buoyant|improv\w*|recover\w*|encouraging|resilient|momentum|picked up|pick up|tailwinds?|benign|comfortable|stable|steady|record|best[- ]ever|ahead of|upbeat|positive|easing|eased)\b", re.I)
NEGATIVE = re.compile(r"\b(soft\w*|weak\w*|slow\w*|sluggish|muted|pressure\w*|stress\w*|headwinds?|deferr\w*|delay\w*|challeng\w*|declin\w*|subdued|elevated|volatil\w*|uncertain\w*|cautious|deteriorat\w*|tight\w*|impact(ed)?|inflation\w*|warning letter|import alert|observations|setback|lower than expected)\b", re.I)
NEGATED = re.compile(r"\b(no|not|without|limited|minimal|any)\s(\w+\s){0,2}(stress|pressure|slowdown|challenges?|headwinds?|delays?|impact)", re.I)


def hedge_of(s: str) -> str | None:
    for name, rx in HEDGES:
        if rx.search(s):
            return name
    return None


def tone_of(s: str) -> str:
    if NEGATED.search(s):
        return "positive"
    p, n = len(POSITIVE.findall(s)), len(NEGATIVE.findall(s))
    return "positive" if p > n else "negative" if n > p else "neutral"


def theme_of(s: str) -> str | None:
    low = s.lower()
    for name, rx in THEMES:
        if re.search(rx, low):
            return name
    return None


def clauses(sentence: str) -> list[str]:
    """Split where a sentence states two targets: '... 12-14% and EBITDA margins of 16-17% ...',
    or two figures on different bases: '... 1.8% sequentially and 8.2% year on year'."""
    parts = re.split(r";\s|,\s(?:and|but)\s(?=(?:we|management|the company)\s+(?:now\s+|also\s+)?(?:expect|will|should|plan|aim|anticipate|see|remain|hope|are confident)\b)|,?\s(?:and|while|whereas|with)\s(?=(?:our\s|the\s)?(?:ebitda|ebit|revenue|margin|pat|capex|credit|nim|net|gross|aum|loan|export)\w*)|,?\sand\s(?=(?:by\s)?(?:₹|rs\.?\s?)?\d)", sentence, flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def _cid(doc_id: str, quote: str, metric: str | None, n: int = 0) -> str:
    return "cl:" + hashlib.sha1(f"{doc_id}|{quote}|{metric}|{n}".encode()).hexdigest()[:12]


# ------------------------------------------------------------------ classify

def classify(
    sentence: str,
    *,
    doc_id: str,
    doc_kind: str,
    call_period: str | None,
    call_date: date,
    page: int | None,
    section: str | None,
    speaker: str | None,
    role: str,
    prev_sentence: str | None,
    question: str | None,
    threads: set[str],
    is_financial: bool,
    is_it: bool,
    segments: list[str],
) -> list[Claim]:
    """Zero or more claims from one management sentence."""
    s = sentence.strip()
    if role in ("analyst", "moderator") or len(s) < 12:
        return []
    low = s.lower()
    out: list[Claim] = []
    future = bool(FUTURE.search(s))
    past = bool(PAST.search(s)) and not future
    hits = find(s, is_financial, is_it)
    base = dict(doc_id=doc_id, doc_kind=doc_kind, call_period=call_period, page=page, section=section, speaker=speaker, role=role)

    if NOT_COMPANY.search(s) and not COMPANY.search(s):
        th = theme_of(s)
        if th and (future or past or tone_of(s) != "neutral"):
            out.append(Claim(id=_cid(doc_id, s, None), kind="outlook", quote=s, theme=th, tone=tone_of(s), **base))
        return out

    if WITHDRAW.search(s) and not REAFFIRM.search(s):
        ms = [h[0] for h in hits]
        out.append(Claim(id=_cid(doc_id, s, "withdraw"), kind="guidance", metric=ms[0].id if ms else None, metric_label=ms[0].label if ms else None,
                         quote=s, withdraws=True, theme=theme_of(s), tone="negative", **base))
        return out

    # Management confirming a figure the analyst stated.
    if CONFIRM.search(s) and question and not hits:
        qhits = find(question, is_financial, is_it)
        if qhits:
            m = qhits[0][0]
            t = parse_target(question, m)
            per, ptxt, horizon = resolve_period(question, call_date, call_period)
            key = f"{m.id}|{per}"
            if key in threads:
                out.append(Claim(id=_cid(doc_id, s, m.id), kind="guidance", metric=m.id, metric_label=m.label, quote=s, reaffirms=True, period=per,
                                 period_text=ptxt, hedge="expected", confirmed_analyst_figure=True, context_quote=question, theme=theme_of(question), **base))
            elif t and per:
                out.append(Claim(id=_cid(doc_id, s, m.id), kind="guidance", metric=m.id, metric_label=m.label, quote=s, target=t, period=per, period_text=ptxt,
                                 hedge="expected", confirmed_analyst_figure=True, context_quote=question, theme=theme_of(question), **base))
        return out

    if REAFFIRM.search(s):
        ms = [h[0] for h in hits] or [h[0] for h in find(question or "", is_financial, is_it)]
        m = ms[0] if ms else None
        per, ptxt, _ = resolve_period(s, call_date, call_period)
        if not per and m:
            # "We maintain our margin guidance" names no period: use the open thread for that metric.
            open_ = sorted(t.split("|")[1] for t in threads if t.startswith(m.id + "|") and t.split("|")[1] != "None")
            per = open_[-1] if open_ else None
        t = parse_target(s, m) if m else None
        if m and (per or t):
            out.append(Claim(id=_cid(doc_id, s, m.id), kind="guidance", metric=m.id, metric_label=m.label, quote=s, reaffirms=t is None, target=t,
                             period=per, period_text=ptxt, hedge=hedge_of(s) or "firm", context_quote=question if not hits else None, theme=theme_of(s), **base))
            return out

    if not hits:
        th = theme_of(s)
        if th and tone_of(s) != "neutral":
            out.append(Claim(id=_cid(doc_id, s, None), kind="outlook", quote=s, theme=th, tone=tone_of(s), **base))
        return out

    # Numbers and periods that belong to something else are taken out before targets are read:
    # "of which Rs. 280 crore has been spent in the first half", "price increases of 3%", "a tax rate of 25%".
    sc = scrub(s)
    parts = clauses(sc)
    used: set[tuple] = set()
    carried: list = []
    for n, clause in enumerate(parts):
        own = find(clause, is_financial, is_it)
        # "grew 1.8% sequentially and 8.2% year on year": the second clause inherits the metric.
        ch = own or (hits if len(parts) == 1 else carried if re.search(r"\d", clause) else [])
        if not ch:
            continue
        carried = ch
        m, mpos = ch[0][0], (ch[0][1] if own else 0)
        if m.kind == "growth" and not GROWTH_WORDS.search(clause if own else s):
            continue  # "18% of the loan book is unsecured" is a share, not growth
        basis = "yoy" if YOY.search(clause) else "qoq" if QOQ.search(clause) else None
        # Tense per clause: "FY26 revenue grew 12% with margins within our guidance" is about the past.
        cfuture = bool(FUTURE.search(clause)) or (future and not PAST.search(clause)) if len(parts) > 1 else future
        key = (m.id, basis, cfuture)
        if key in used:
            continue
        seg = next((g for g in segments if g.lower() in clause.lower()), None)
        if cfuture:
            per, ptxt, horizon = resolve_period(clause, call_date, call_period)
            if not per:
                per, ptxt, horizon = resolve_period(sc, call_date, call_period)
            if not per and prev_sentence:
                per, ptxt, horizon = resolve_period(prev_sentence, call_date, call_period)
            t = parse_target(clause, m)
            d = local_direction(clause, mpos) if not t else None
            if per and (t or d):
                if not t:
                    t = Target(kind="direction", direction=d, text=clause[:80], reading=f"Direction only: {m.label.lower()} {'to rise' if d == 'up' else 'to fall' if d == 'down' else 'to stay flat'}. No number was given, so none is used.")
                out.append(Claim(id=_cid(doc_id, s, m.id, n), kind="guidance", metric=m.id, metric_label=m.label, segment=seg, quote=s, target=t, period=per,
                                 period_text=ptxt, hedge=hedge_of(clause) or hedge_of(s) or "expected", theme=theme_of(clause), tone=tone_of(clause), **base))
            else:
                out.append(Claim(id=_cid(doc_id, s, m.id, n), kind="outlook", metric=m.id, metric_label=m.label, segment=seg, quote=s,
                                 theme=theme_of(clause) or m.label, tone=tone_of(clause), **base))
            used.add(key)
        else:
            per, ptxt, _ = resolve_period(clause, call_date, call_period, past=True)
            if not per:
                per, ptxt, _ = resolve_period(s, call_date, call_period, past=True)
            per = per or call_period
            t = parse_target(clause, m)
            if t and t.kind == "words":
                t = None
            d = local_direction(clause, mpos)
            if t or d:
                out.append(Claim(id=_cid(doc_id, s, m.id, n), kind="assertion", metric=m.id, metric_label=m.label, segment=seg, quote=s, target=t,
                                 period=per, period_text=ptxt, basis_hint=basis, theme=theme_of(clause), tone=tone_of(clause), **base))
            else:
                out.append(Claim(id=_cid(doc_id, s, m.id, n), kind="outlook", metric=m.id, metric_label=m.label, quote=s, theme=theme_of(clause) or m.label, tone=tone_of(clause), **base))
            used.add(key)
    if not out:
        # No metric claim survived (e.g. "cash generation remained strong, with OCF at 84% of EBITDA"): keep it as commentary.
        th = theme_of(s)
        if th and tone_of(s) != "neutral":
            out.append(Claim(id=_cid(doc_id, s, None), kind="outlook", quote=s, theme=th, tone=tone_of(s), **base))
    return out


_OF_WHICH = re.compile(r",?\s*of which\b(?:[^.;]|\.(?=\s?\d)|(?<=rs)\.)*", re.I)
_OWNED_QTY = re.compile(r"\b(price|pricing|tariff|wage|salary|freight|fuel|raw material|input cost)s?\s+(increase|hike|cut|rise|reduction|correction)s?\s+of\s+(about\s+|around\s+)?[\d.]+\s?%"
                        r"|\b(tax rate|payout( ratio)?|dividend payout)\b[^.;%]{0,30}?[\d.]+\s?%", re.I)


def scrub(s: str) -> str:
    """Blank out quantities that belong to another noun, keeping sentence length so positions still line up."""
    s = _OF_WHICH.sub(lambda m: " " * len(m.group(0)), s)
    return _OWNED_QTY.sub(lambda m: re.sub(r"[\d.]+\s?%", lambda x: "#" * len(x.group(0)), m.group(0)), s)


GROWTH_WORDS = re.compile(r"\bgr[eo]w\w*|growth|increas\w*|\bris(e|en|es|ing)\b|\brose\b|\bup\b|declin\w*|\bfell\b|\bfall\w*|\bdown\b|expan\w*|contract\w*|jump\w*|surg\w*|\bdip\w*|\bdoubl\w*|\bflat\b|\bcagr\b", re.I)


def local_direction(clause: str, metric_pos: int) -> str | None:
    """Direction stated about the metric itself: the verb must follow the metric within a few words.

    "Margins expanded" and "we expect margins to improve" give a direction;
    "margins absorbed the wage increase" does not, because "increase" belongs
    to the wages.
    """
    tail = clause[metric_pos:]
    words = re.findall(r"[\w\-%.]+", tail)
    window = " ".join(words[:7])
    d = direction(window)
    if d:
        return d
    # A verb directly in front of the metric: "reduce debt", "improve margins", "grow revenue".
    before = re.findall(r"[\w\-]+", clause[:metric_pos])[-2:]
    return direction(" ".join(before)) if before else None


# ------------------------------------------------------------------ gates

def _nums(s: str) -> set[str]:
    return {re.sub(r"\.0+$", "", t.replace(",", "")) for t in NUM_TOKEN.findall(s)}


def gates(c: Claim, page_text: dict[int, str], turn_text: str | None) -> Claim:
    """G1 quote on page, G2 speaker is management, G3 numbers in quote, G4 period stated."""
    g: dict[str, object] = {}
    q = norm(c.quote).lower()
    pages = [c.page] if c.page else []
    pages += [p for p in (c.page - 1 if c.page else None, c.page + 1 if c.page else None) if p]
    hit = next((p for p in pages if p in page_text and q[:120] in re.sub(r"\s+", " ", norm(page_text[p]).lower())), None)
    if hit is None:
        hit = next((p for p, t in page_text.items() if q[:120] in re.sub(r"\s+", " ", norm(t).lower())), None)
    g["quote_on_page"] = hit is not None
    if hit is not None and hit != c.page:
        c.page = hit
    g["speaker"] = c.role
    src = (c.context_quote or "") if c.confirmed_analyst_figure else c.quote
    if c.target and c.target.kind != "direction":
        g["numbers_in_quote"] = _nums(c.target.text) <= _nums(src) and c.target.text.lower() in src.lower()
    else:
        g["numbers_in_quote"] = True
    if c.kind == "guidance" and not c.reaffirms and not c.withdraws and c.period:
        stated = bool(c.period_text) and (c.period_text.lower() in c.quote.lower() or (turn_text or "").lower().find(c.period_text.lower()) >= 0)
        g["period_stated"] = stated
    c.gates = g
    return c


def accept(c: Claim) -> Claim | None:
    """Apply gate outcomes: reject, downgrade, or keep with a flag."""
    if not c.gates.get("quote_on_page"):
        return None
    if c.role in ("analyst", "moderator"):
        return None
    if not c.gates.get("numbers_in_quote", True):
        return None
    if c.kind == "guidance" and c.gates.get("period_stated") is False:
        c.kind, c.target, c.period, c.hedge = "outlook", None, None, None
    return c
