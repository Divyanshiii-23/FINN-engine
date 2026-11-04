"""Ask FINN: questions about one company, answered only from its primary documents.

    question ─► scope check ─► intent, topics, periods
             ─► retrieve passages (BM25 over transcripts, decks, annual reports, statement tables)
             ─► retrieve facts (reported figures, FINN computations, ledger, findings)
             ─► compose blocks: fact | management | interpretation | gap
             ─► validate every block (citations resolve; every number is in the cited evidence)
             ─► answer, with status: answered | partial | insufficient | out_of_scope

There is no general model knowledge in this path. Without a model, answers are
composed by fixed rules from the evidence. With one (`complete`), the model
writes from an evidence pack and each block it writes must cite pack items,
use only numbers found in what it cites, and share most of its content words
with that evidence. Blocks that fail are dropped; if nothing factual survives,
the rule-written answer is returned with the reason.

Passages are built during the research run (`build_passages`) and stored next
to the report, so answering a question never re-reads a PDF.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from . import periods as P
from . import transcript as T
from .claims import FUTURE, theme_of, tone_of
from .models import Doc
from .pdftext import PdfText, sentences

# ------------------------------------------------------------------ passages


def build_passages(doc: Doc, pdf: PdfText) -> list[dict]:
    """Citable passages from one parsed document, each with its page and context."""
    out: list[dict] = []
    base = {"doc_id": doc.id, "doc_kind": doc.kind, "period": doc.period}

    def add(page: int, text: str, **kw) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 25:
            return
        out.append({"id": f"p:{doc.id[2:]}:{page}:{len(out)}", "page": page, "text": text, **base, **kw})

    if doc.kind == "transcript":
        tr = T.parse(pdf)
        question: str | None = None
        for turn in tr.turns:
            if turn.role == "moderator":
                continue
            if turn.role == "analyst":
                question = f"{turn.speaker}: {turn.text[:300]}"
            ctx = {"question": question} if turn.role != "analyst" and turn.section == "Q&A" and question else {}
            buf: list[str] = []
            page = turn.page_start
            pos = 0
            joined = " ".join(t for _, t in turn.lines)
            starts = []
            for p, t in turn.lines:
                starts.append((pos, p))
                pos += len(t) + 1
            cursor = 0
            for s in sentences(joined):
                i = joined.find(s, cursor)
                cursor = max(cursor, i)
                if not buf:
                    page = next((p for st, p in reversed(starts) if st <= max(i, 0)), turn.page_start)
                buf.append(s)
                if len(buf) == 3:
                    add(page, " ".join(buf), section=turn.section, speaker=turn.speaker + (f", {turn.title}" if turn.title else ""), role=turn.role, **ctx)
                    buf = []
            if buf:
                add(page, " ".join(buf), section=turn.section, speaker=turn.speaker + (f", {turn.title}" if turn.title else ""), role=turn.role, **ctx)
    elif doc.kind == "results":
        for p in range(1, pdf.pages + 1):
            lines = [l.text for l in pdf.lines if l.page == p]
            if len(lines) < 4:
                continue
            title = next((l for l in lines if re.search(r"statement|segment|notes", l, re.I)), lines[0])
            add(p, " | ".join(lines), section=title, role="company", table=True)
    else:
        for p in range(1, pdf.pages + 1):
            lines = [l.text for l in pdf.lines if l.page == p]
            if not lines:
                continue
            title = lines[0]
            if doc.kind == "presentation":
                add(p, " · ".join(lines), section=title, role="company")
                continue
            ss = sentences(" ".join(lines[1:]))
            for i in range(0, len(ss), 3):
                add(p, " ".join(ss[i:i + 3]), section=title, role="company")
    return out


# ------------------------------------------------------------------ retrieval

STOP = set("""a an and are as at be been being but by can could did do does doing for from had has have having how i if in into is it its
of on or our over so such than that the their them then there these they this those to was we were what when where which while who why
will with would you your about between last two latest recent did does management company s per vs""".split())


def _stem(w: str) -> str:
    """Crude suffix stripping; a trailing 'e' is dropped too so price/prices/priced and wage/wages meet."""
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)] + ("y" if suf == "ies" else "e" if suf == "es" else "")
            break
    return w[:-1] if len(w) > 4 and w.endswith("e") else w


# Domain paraphrases: the documents' word on the right. Lexical search can't otherwise connect them.
SYNONYMS = {"logistic": ["freight"], "transport": ["freight"], "fda": ["usfda"], "borrow": ["fund"], "expenditur": ["capex"],
            "salary": ["wag"], "salari": ["wag"], "hik": ["wag"], "npa": ["stag"], "bad": ["stag", "npa"], "realization": ["realis", "pric"],
            "realis": ["pric"], "workforc": ["utilis"], "staff": ["utilis", "wag"], "plant": ["facility", "unit"]}


def toks(s: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z][a-z0-9]+", s.lower()) if w not in STOP]


class Index:
    """BM25 over passages. Small and exact: no embeddings, so every match can be explained by its words."""

    def __init__(self, passages: list[dict]):
        self.p = passages
        self.docs = [Counter(toks(x["text"] + " " + (x.get("section") or ""))) for x in passages]
        self.len = [sum(c.values()) for c in self.docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1
        df: Counter = Counter()
        for c in self.docs:
            df.update(c.keys())
        n = len(passages)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, terms: list[str], keep: Callable[[dict], bool] = lambda p: True, k: int = 6, min_score: float = 1.2) -> list[tuple[float, dict]]:
        # Terms may arrive raw ("costs") or already stemmed by toks(); never stem twice ("utilis" -> "utili").
        base = [x if x in self.idf else _stem(x) for x in terms]
        q = [t for t in dict.fromkeys(base + [y for x in base for y in SYNONYMS.get(x, [])])]
        out = []
        for i, c in enumerate(self.docs):
            if not keep(self.p[i]):
                continue
            s = 0.0
            for t in q:
                f = c.get(t, 0)
                if f:
                    s += self.idf.get(t, 0) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.len[i] / self.avg))
            if s >= min_score:
                out.append((round(s, 3), self.p[i]))
        return sorted(out, key=lambda x: -x[0])[:k]


# ------------------------------------------------------------------ understanding the question

TOPICS: dict[str, dict] = {
    "margins": {"words": r"margin|profitab|ebitda|ebit\b|(?<!credit )cost|expense", "terms": "margin margins ebitda ebit profitability cost costs expenses pricing realisation fuel input wage", "themes": {"Margins", "Input costs", "Pricing"}},
    "revenue": {"words": r"revenue|sales|top[- ]?line|growth|grow|turnover", "terms": "revenue sales growth grew demand volume", "themes": {"Demand", "Client spending", "Deal pipeline"}},
    "profit": {"words": r"profit|earnings(?! call)|\bpat\b|net income", "terms": "profit pat earnings", "themes": set()},
    "cash": {"words": r"cash|ocf|working capital|receivabl|conversion|free cash", "terms": "cash flow operating generation conversion working capital receivables inventory collections", "themes": {"Cash generation", "Working capital"}},
    "capacity": {"words": r"capacit|capex|expansion|plant|commission|greenfield|brownfield|utili[sz]", "terms": "capacity capex expansion plant commissioning grinding unit greenfield brownfield utilisation mtpa", "themes": {"Capacity and capex"}},
    "debt": {"words": r"debt|borrow|leverage|deleverag", "terms": "debt net borrowings leverage repay", "themes": {"Debt"}},
    "asset_quality": {"words": r"asset quality|npa|credit cost|stress|delinquen|collection|slippage", "terms": "asset quality credit cost stress collection slippages npa provisions unsecured", "themes": {"Asset quality"}},
    "demand": {"words": r"demand|volume|offtake", "terms": "demand volume offtake markets", "themes": {"Demand"}},
    "pricing": {"words": r"pric|realis|realiz", "terms": "pricing prices realisations", "themes": {"Pricing"}},
    "clients": {"words": r"client|discretionary|deal|pipeline|tcv", "terms": "client clients discretionary spending budgets decision deal pipeline", "themes": {"Client spending", "Deal pipeline"}},
    "regulation": {"words": r"regulat|usfda|warning letter|compliance|inspection", "terms": "regulatory usfda warning letter facility remediation inspection", "themes": {"Regulation"}},
    "guidance": {"words": r"guidance|guide|target|outlook", "terms": "guidance expect target outlook", "themes": set()},
}

OUT_OF_SCOPE = re.compile(r"\b(should i (buy|sell|invest|hold)|buy or sell|target price|price target|fair value|intrinsic value|is it a (good|bad) (buy|investment)|"
                          r"will the (stock|share|price)|(predict|forecast) (the )?(stock|share|price|returns?)|"
                          # "recommend" only as advice to the user, not management's own words ("what did they predict for capex")
                          r"(do|would|can|could) you (recommend|suggest)|recommend (buying|selling|holding|(this|the|a) (stock|share)s?)|your (recommendation|view on the stock)|"
                          r"undervalued|overvalued|multibagger)\b", re.I)
GENERAL = re.compile(r"\b(capital of|who won|weather|recipe|world cup|president of|prime minister)\b", re.I)


def intent_of(q: str) -> str:
    low = q.lower()
    if OUT_OF_SCOPE.search(low):
        return "out_of_scope"
    if re.search(r"contradict|inconsisten|disagree|mismatch|don'?t (match|add up)|narrative", low):
        return "contradictions"
    if re.search(r"(what|how).{0,30}(chang|differ|shift)|compare.{0,20}call|between the (last|latest) (two|2) (earnings )?calls", low) and re.search(r"call|transcript|quarter", low):
        return "call_diff"
    if re.search(r"promis|guid|commit|target|plan(s|ned)?\b|said .{0,20}would|expect(ed|ation)|predict|forecast|outlook", low):
        return "promises"
    if re.search(r"(what|how) (did|has|have|does) management (say|said|describe|talk|comment|view)|management'?s? (commentary|view|comments|tone|narrative) (on|about)|what (is|was) said about", low):
        return "said_about"
    if re.search(r"(operating )?cash flow.{0,40}(support|back|match|cover)|(support|back).{0,30}profit|quality of earnings|cash conversion|converting.{0,20}cash", low):
        return "cash_vs_profit"
    if re.search(r"^\s*why\b|what (caused|drove|explains)|reason", low):
        return "explain_change"
    if re.search(r"trend|over time|trajectory|history|how ha(s|ve) .{0,40}(moved|changed|grown)", low):
        return "trend"
    return "lookup"


def topics_of(q: str) -> list[str]:
    low = q.lower()
    return [k for k, v in TOPICS.items() if re.search(v["words"], low)]


def direction_of(q: str) -> str | None:
    low = q.lower()
    if re.search(r"declin|fall|fell|drop|decreas|contract|weak|lower|shr[iu]nk|compress|down", low):
        return "down"
    if re.search(r"ris(e|ing)|rose|improv|increas|expan|grew|grow|higher|up\b", low):
        return "up"
    return None


def period_of(q: str) -> str | None:
    m = re.search(r"\b(q[1-4])\s?fy\s?'?(\d{2})\b", q, re.I)
    if m:
        return f"{m.group(1).upper()} FY{m.group(2)}"
    m = re.search(r"\b(h[12])\s?fy\s?'?(\d{2})\b", q, re.I)
    if m:
        return f"{m.group(1).upper()} FY{m.group(2)}"
    m = re.search(r"\bfy\s?'?(\d{2})\b", q, re.I)
    return f"FY{m.group(1)}" if m else None


# ------------------------------------------------------------------ answer building


@dataclass
class Answer:
    question: str
    intent: str
    topics: list[str]
    blocks: list[dict] = field(default_factory=list)
    passages: dict[str, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    whole: str | None = None       # a named year/half answered through its latest quarter
    period_gap: bool = False       # the named period isn't in the filings read

    def add(self, kind: str, text: str, cites: list[str], **kw) -> None:
        self.blocks.append({"kind": kind, "text": text, "cites": [c for c in dict.fromkeys(cites) if c], **kw})

    def said(self, p: dict, score: float | None = None) -> str:
        self.passages[p["id"]] = {**p, **({"score": score} if score is not None else {})}
        return p["id"]


class Asker:
    def __init__(self, report: dict, passages: list[dict]):
        self.r, self.f, self.ps = report, report["facts"], passages
        self.docs = {d["id"]: d for d in report["documents"]}
        self.ix = Index(passages)
        self.fin = report["identity"]["is_financial"]
        self.ledger = report["ledger"]
        self.claims = report["claims"]

    # -------------------------------------------------- helpers
    def fact(self, fid: str | None) -> dict | None:
        return self.f.get(fid or "")

    def disp(self, fid: str) -> str:
        return (self.f[fid].get("display") or "").replace("-", "−", 1) if self.f[fid].get("display", "").startswith("-") else self.f[fid].get("display") or ""

    def quarters(self) -> list[str]:
        return list(self.r["sections"]["trajectory"]["quarters"])

    def calls(self) -> list[dict]:
        ds = [d for d in self.r["documents"] if d["kind"] == "transcript" and d["status"] == "parsed" and d.get("period")]
        return sorted(ds, key=lambda d: P.q_index(d["period"]) if d["period"].startswith("Q") else 0)

    def margin_key(self) -> tuple[str, str]:
        """EBIT for companies that guide on EBIT (IT services), EBITDA otherwise."""
        if self.r["identity"].get("is_it_services") or any(e["metric"] == "ebit_margin" for e in self.ledger):
            return "ebit", "EBIT margin"
        return "ebitda", "EBITDA margin"

    def search(self, a: Answer, terms: str, *, roles=("management", "company", "unknown"), docs: set[str] | None = None, periods: set[str] | None = None,
               kinds: set[str] | None = None, k: int = 4, future: bool | None = None, min_score: float = 1.2) -> list[str]:
        def keep(p: dict) -> bool:
            if p.get("role") not in roles:
                return False
            if docs is not None and p["doc_id"] not in docs:
                return False
            if periods is not None and p.get("period") not in periods:
                return False
            if kinds is not None and p["doc_kind"] not in kinds:
                return False
            if future is not None and bool(FUTURE.search(p["text"])) != future:
                return False
            return True
        hits = self.ix.search(toks(terms), keep, k=k, min_score=min_score)
        return [a.said(p, s) for s, p in hits]

    # -------------------------------------------------- intents
    def explain_change(self, a: Answer, q: str) -> None:
        topic = next((t for t in a.topics if t in ("margins", "revenue", "profit", "cash", "debt")), None)
        if topic == "margins" or topic is None and "margin" in q.lower():
            return self._why_margin(a, q)
        if topic in ("revenue", "profit"):
            return self._why_growth(a, q, "revenue" if topic == "revenue" else "pat")
        if topic == "cash":
            return self.cash_vs_profit(a, q)
        self.lookup(a, q)

    def _period_for(self, a: Answer, q: str) -> str | None:
        """The quarter to analyse. A named quarter is used as is; a named year or half is
        answered through its latest quarter, and the answer says so; a period the filings
        don't cover gets a gap, never a silent switch to another period."""
        p, qs = period_of(q), self.quarters()
        if not qs:
            return None
        if not p:
            return qs[-1]
        if p in qs:
            return p
        inside = [x for x in (P.quarters(p) or []) if x in qs]
        if not inside:
            a.add("gap", f"The question names {p}, but the results read cover {qs[0]} to {qs[-1]}, so FINN can't answer for {p}.", [])
            a.period_gap = True
            return None
        a.add("note", f"You asked about {p}. FINN explains changes quarter by quarter, so this answers for {inside[-1]}, the latest quarter of {p} in the filings read.", [])
        a.whole = p
        return inside[-1]

    def _why_margin(self, a: Answer, q: str) -> None:
        if self.fin:
            a.add("gap", "Lenders don't report an operating margin in their statements; ask about net interest income, credit cost or profit instead.", [])
            return
        num, label = self.margin_key()
        per = self._period_for(a, q)
        if not per:
            if not a.period_gap:
                a.add("gap", "No results filing could be read, so there is no reported margin to explain.", [])
            return
        if a.whole:
            w, wy = self.fact(f"c:{a.whole.replace(' ', '')}:{num}_margin"), self.fact(f"c:{P.shift_year(a.whole).replace(' ', '')}:{num}_margin")
            if w and wy:
                a.add("fact", f"For {a.whole} as a whole, the {label[0].lower() + label[1:] if not label[:2].isupper() else label} was {w['display']} against {wy['display']} in {P.shift_year(a.whole)}.", [w["id"], wy["id"]], info="computed")
        yoy, qoq = P.shift_year(per), P.prev_q(per)
        m = self.fact(f"c:{per.replace(' ', '')}:{num}_margin")
        my = self.fact(f"c:{yoy.replace(' ', '')}:{num}_margin")
        mq = self.fact(f"c:{qoq.replace(' ', '')}:{num}_margin")
        if not m or not my:
            a.add("gap", f"The {label.lower()} for {per} and {yoy} couldn't both be computed from the filings read.", [])
            return
        cy = self.fact(f"c:{per.replace(' ', '')}:{num}_margin_chg_{yoy.replace(' ', '')}")
        cq = self.fact(f"c:{per.replace(' ', '')}:{num}_margin_chg_{qoq.replace(' ', '')}")
        dy = (m["value"] - my["value"]) * 100
        dq = cq["value"] if cq else None
        want = direction_of(q)
        moved = "fell" if dy < 0 else "rose"
        a.add("fact", f"{label} was {m['display']} in {per} against {my['display']} in {yoy}: " + (f"{cy['display']} year on year" if cy else f"it {moved}")
              + (f"; against {qoq} ({mq['display']}) the change was {cq['display']}." if mq and cq else "."),
              [m["id"], my["id"]] + [x["id"] for x in (mq, cy, cq) if x], info="computed")
        if want and (want == "down") != (dy < 0):
            a.add("note", f"The question assumes the margin {'declined' if want == 'down' else 'rose'}, but year on year it {moved}.", [m["id"], my["id"]])
        lines = self.r.get("cost_lines", {}).get(per)
        base = self.r.get("cost_lines", {}).get(yoy)
        if lines and base:
            moves = []
            for key, (lab, share, fid, chg) in lines.items():
                if key in base and yoy in chg:
                    moves.append((chg[yoy][0], lab, fid, base[key][2], chg[yoy][1]))
            moves.sort(key=lambda x: -abs(x[0]))
            big = [x for x in moves if abs(x[0]) >= 0.25][:3]
            if big:
                parts = "; ".join(f"{lab.lower()} {self.f[f2]['display']} → {self.f[f1]['display']} of revenue ({self.f[c]['display']})" for d, lab, f1, f2, c in big)
                a.add("fact", f"By cost line, as a share of revenue ({yoy} → {per}): {parts}. A cost line rising as a share of revenue lowers the margin by the same amount.",
                      [x for d, lab, f1, f2, c in big for x in (f1, f2, c)], info="computed")
            else:
                a.add("fact", f"No single cost line moved by more than a quarter of a percentage point of revenue between {yoy} and {per}.", [x[4] for x in moves[:3]], info="computed")
        g = self.fact(f"c:{per.replace(' ', '')}:revenue_growth_{yoy.replace(' ', '')}")
        if g:
            a.add("fact", f"Revenue {'fell' if g['value'] < 0 else 'grew'} {g['display'].lstrip('+-')} year on year in {per}, so fixed costs were spread over {'less' if g['value'] < 0 else 'more'} revenue.", [g["id"]], info="computed")
        call = next((d for d in self.calls() if d["period"] == per), None)
        pids = self.search(a, "margin margins cost costs fuel price prices realisations pressure input wage remediation pricing", docs={call["id"]} if call else None,
                           periods=None if call else {per}, k=3, min_score=0.8)
        if pids:
            a.add("management", f"What management said on the {per} call about margins and costs:", pids)
        else:
            a.add("gap", f"No {per} call transcript passage discusses margins or costs, so management's explanation isn't available from the documents read.", [])
        contra = [d for d in self.r["sections"]["nvn"]["discrepancies"] if d["rule"] == "commentary_vs_numbers" and "margin" in d["text"] and per in d["text"]]
        if contra:
            a.add("interpretation", contra[0]["text"], contra[0]["evidence"])
        top = (big[0][1].lower() if lines and base and big else None) if dy < 0 else None
        if dy < 0:
            a.add("interpretation", f"The statements show where the margin went{f' (mainly {top})' if top else ''}; they don't show why. Management's own explanation is quoted above, "
                  "and FINN doesn't add causes the documents don't state.", [m["id"], my["id"]])

    def _why_growth(self, a: Answer, q: str, key: str) -> None:
        per = self._period_for(a, q)
        if not per:
            if not a.period_gap:
                a.add("gap", "No results filing could be read.", [])
            return
        yoy = P.shift_year(per)
        g = self.fact(f"c:{per.replace(' ', '')}:{key}_growth_{yoy.replace(' ', '')}")
        name = "Revenue" if key == "revenue" else "Profit after tax"
        if not g:
            a.add("gap", f"{name} growth for {per} couldn't be computed from the filings read.", [])
            return
        a.add("fact", f"{name} {'fell' if g['value'] < 0 else 'grew'} {g['display'].lstrip('+-')} year on year in {per}.", [g["id"]] + g.get("inputs", []), info="computed")
        want = direction_of(q)
        if want and (want == "down") != (g["value"] < 0):
            a.add("note", f"The question assumes {name.lower()} {'fell' if want == 'down' else 'rose'}, but in {per} it {'grew' if g['value'] >= 0 else 'fell'}.", [g["id"]])
        segs = self.r["sections"]["business"]["segments"]
        if segs and key == "revenue":
            parts = [(s["name"], s["growth_fact"]) for s in segs if s.get("growth_fact")]
            if parts:
                a.add("fact", "By segment, year on year: " + "; ".join(f"{n} {self.f[fid]['display']}" for n, fid in parts) + ".", [fid for _, fid in parts], info="computed")
        call = next((d for d in self.calls() if d["period"] == per), None)
        pids = self.search(a, TOPICS["revenue"]["terms"] + " " + TOPICS["demand"]["terms"] + " " + TOPICS["clients"]["terms"] + " pricing launches delayed",
                           docs={call["id"]} if call else None, k=3, min_score=0.8)
        if pids:
            a.add("management", f"What management said on the {per} call:", pids)
        a.add("interpretation", "The statements give the size of the change; the reasons are management's, as quoted. FINN doesn't add causes the documents don't state.", [g["id"]])

    def call_diff(self, a: Answer, q: str) -> None:
        calls = self.calls()
        if len(calls) < 2:
            a.add("gap", f"Only {len(calls)} call transcript was found, so there is nothing to compare.", [])
            return
        c1, c2 = calls[-2], calls[-1]
        a.notes.append(f"Compared the {c1['period']} and {c2['period']} call transcripts.")
        if P.q_index(c2["period"]) - P.q_index(c1["period"]) > 1:
            gap_q = [P.from_index(i) for i in range(P.q_index(c1["period"]) + 1, P.q_index(c2["period"]))]
            a.add("gap", f"No {', '.join(gap_q)} call transcript was found, so the last two calls read are {c1['period']} and {c2['period']}.", [])
        # Everything filed for each quarter counts: a target cut in the results-day presentation and repeated on the call was cut that quarter.
        q1 = {d["id"] for d in self.r["documents"] if d.get("period") == c1["period"] and d["kind"] in ("transcript", "presentation", "press_release")}
        q2 = {d["id"] for d in self.r["documents"] if d.get("period") == c2["period"] and d["kind"] in ("transcript", "presentation", "press_release")}
        changes = []
        for e in self.ledger:
            if e["kind"] != "guidance":
                continue
            h2 = [h for h in e.get("history", []) if h["doc_id"] in q2 and h["change"] != "also stated"]
            h1 = [h for h in e.get("history", []) if h["doc_id"] in q1]
            for h in h2:
                if h["change"] in ("also stated",):
                    continue
                prev = (h1[-1]["target"] if h1 and h1[-1].get("target") else None)
                what = {"first": "first stated", "reiterated": "reiterated", "raised": "raised", "lowered": "lowered", "changed": "changed", "softened": "restated only in words",
                        "withdrawn": "withdrawn", "not repeated": "not repeated", "differs": "stated differently in another document"}[h["change"]]
                tgt = f" {h['target']}" if h.get("target") and h["change"] not in ("not repeated", "withdrawn", "softened") else ""
                changes.append((e, h, f"{e['metric_label']} {e.get('period')}: {what}{tgt}" + (f" (was {prev} on the {c1['period']} call)" if prev and h["change"] in ("raised", "lowered", "changed", "softened", "not repeated") else "")))
        if changes:
            a.add("fact", f"Guidance, {c1['period']} call → {c2['period']} call: " + "; ".join(t for _, _, t in changes) + ".",
                  [h.get("fact_id") for _, h, _ in changes] + [x["fact_id"] for e, h, _ in changes for x in e["history"] if x["doc_id"] in q1 and x.get("fact_id")], info="guidance")
        else:
            a.add("note", f"No guidance figure changed between the {c1['period']} and {c2['period']} calls.", [])
        tone: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for c in self.claims:
            if c["doc_id"] in (c1["id"], c2["id"]) and c.get("theme") and c["tone"] != "neutral" and c.get("fact_id"):
                tone[c["theme"]][c["doc_id"]].append(c)
        shifts = []
        for th, per_doc in tone.items():
            def t_of(cs: list[dict]) -> str | None:
                p, n = sum(x["tone"] == "positive" for x in cs), sum(x["tone"] == "negative" for x in cs)
                return None if not cs else "positive" if p > n else "negative" if n > p else "mixed"
            t1, t2 = t_of(per_doc.get(c1["id"], [])), t_of(per_doc.get(c2["id"], []))
            if t1 != t2:
                ev = [x["fact_id"] for x in per_doc.get(c1["id"], [])[:1] + per_doc.get(c2["id"], [])[:1]]
                shifts.append((th, t1, t2, ev))
        for th, t1, t2, ev in shifts:
            if t1 and t2:
                a.add("management", f"{th}: tone went from {t1} on the {c1['period']} call to {t2} on the {c2['period']} call.", ev, info="assertion")
            elif t2:
                a.add("management", f"{th}: came up on the {c2['period']} call ({t2}), not on the {c1['period']} call.", ev, info="assertion")
            else:
                a.add("management", f"{th}: discussed on the {c1['period']} call ({t1}), not mentioned on the {c2['period']} call.", ev, info="assertion")
        num, label = self.margin_key()
        rows = []
        for key, lab in (("revenue", "revenue"), (num + "_margin", label.lower())):
            f1 = self.fact(f"c:{c1['period'].replace(' ', '')}:{key}") or self.fact(f"r:pl:{c1['period'].replace(' ', '')}:{key}")
            f2 = self.fact(f"c:{c2['period'].replace(' ', '')}:{key}") or self.fact(f"r:pl:{c2['period'].replace(' ', '')}:{key}")
            if f1 and f2:
                rows.append((lab, f1, f2))
        if rows:
            a.add("fact", f"Reported between the two quarters: " + "; ".join(f"{lab} {f1['display']} in {c1['period']} and {f2['display']} in {c2['period']}" for lab, f1, f2 in rows) + ".",
                  [x["id"] for _, f1, f2 in rows for x in (f1, f2)], info="reported")
        if changes or shifts:
            a.add("interpretation", self._diff_reading(changes, shifts, c2["period"]), [h.get("fact_id") for _, h, _ in changes][:4] + [e for *_, ev in shifts for e in ev][:4])

    def _diff_reading(self, changes: list, shifts: list, p2: str) -> str:
        quiet = [e for e, h, _ in changes if h["change"] in ("not repeated", "withdrawn", "softened")]
        cuts = [e for e, h, _ in changes if (h["change"] == "lowered" and e.get("better", "up") == "up") or (h["change"] == "raised" and e.get("better") == "down")]
        neg = [th for th, t1, t2, _ in shifts if t2 == "negative"]
        bits = []
        if quiet:
            behind = [e for e in quiet if "behind" in (e.get("status_note") or "")]
            bits.append(f"{len(quiet)} target{'s' if len(quiet) > 1 else ''} went quiet on the {p2} call" + (f", {len(behind)} of them while already behind" if behind else ""))
        if cuts:
            bits.append(f"{len(cuts)} target{'s were' if len(cuts) > 1 else ' was'} cut")
        if neg:
            bits.append(f"tone turned cautious on {', '.join(t.lower() for t in neg)}")
        if not bits:
            return "The two calls are broadly consistent on the targets and themes FINN tracks."
        return "Between the two calls: " + "; ".join(bits) + ". Read together, the narrative became more cautious than the earlier call."

    def cash_vs_profit(self, a: Answer, q: str) -> None:
        if self.fin:
            a.add("gap", "For a lender, operating cash flow includes the growth of the loan book, so comparing it with profit doesn't measure earnings quality. Ask about credit cost or asset quality instead.", [])
            return
        cred = self.r.get("credibility", {})
        ind = next((i for i in cred.get("indicators", []) if i["id"] == "cash"), None)
        rows = [r for r in (ind or {}).get("rows", []) if r.get("ocf_pat")]
        if not rows:
            a.add("gap", "No full-year cash flow statement was found in the filings read, so cash against profit can't be compared.", [])
            return
        parts = "; ".join(f"{r['period']} {self.f[r['ocf_pat']]['display']} of PAT and {self.f[r['ocf_ebitda']]['display']} of EBITDA" for r in rows if r.get("ocf_ebitda"))
        a.add("fact", f"Operating cash flow by year: {parts}.", [x for r in rows for x in (r["ocf_pat"], r["ocf_ebitda"])], info="computed")
        cq = self.r["sections"]["cash_quality"]
        last = cq["periods"][-1] if cq["periods"] else None
        if last and last.startswith("H"):
            row = {r_["label"]: r_["values"][-1] for r_ in cq["rows"]}
            ids = [row.get(k) for k in ("OCF ÷ PAT", "OCF ÷ EBITDA", "Free cash flow")]
            if all(ids):
                a.add("fact", f"In {last}: OCF was {self.f[ids[0]]['display']} of PAT and {self.f[ids[1]]['display']} of EBITDA; free cash flow was {self.disp(ids[2])}.", ids, info="computed")
        for fl in cq.get("flags", []):
            a.add("fact", fl["text"], fl["evidence"], info="computed")
        said = (ind or {}).get("management_said") or []
        if said:
            a.add("management", "What management said about cash:", said[:3])
        pids = [p for p in self.search(a, TOPICS["cash"]["terms"], roles=("management",), kinds={"transcript", "presentation", "annual_report"}, k=3, min_score=1.5)
                if p not in {self.f[x].get("quote") for x in said}]
        quotes = {self.f[x].get("quote", "")[:60] for x in said}
        pids = [p for p in pids if a.passages[p]["text"][:60] not in quotes and not any(qq and qq in a.passages[p]["text"] for qq in quotes)]
        if pids:
            a.add("management", "Other passages on cash and working capital:", pids[:2])
        vals = [r["ocf_pat_value"] for r in rows if r.get("ocf_pat_value") is not None]
        weak_now = any(f["tone"] == "bear" for f in cq.get("flags", []))
        cites = [r["ocf_pat"] for r in rows]
        if vals and min(vals) >= 1.0 and not weak_now:
            a.add("interpretation", "On these years, yes: operating cash flow exceeded reported profit every year, and the latest half shows no warning sign FINN tests for.", cites)
        elif vals and min(vals) >= 1.0:
            a.add("interpretation", "Over full years, operating cash flow has exceeded reported profit; the latest half is weaker (see the flags above), so the support is less clear for the current year.",
                  cites + [x for f in cq.get("flags", []) for x in f["evidence"]])
        else:
            a.add("interpretation", "Not consistently: in at least one year operating cash flow fell short of reported profit, which is the pattern to examine in working capital and other operating items.", cites)
        for cid in (ind or {}).get("contradictions", []):
            d = next((x for x in self.r["sections"]["nvn"]["discrepancies"] if x["id"] == cid), None)
            if d:
                a.add("interpretation", d["text"], d["evidence"])

    def promises(self, a: Answer, q: str) -> None:
        topics = [t for t in a.topics if t != "guidance"] or ["guidance"]
        metric_for = {"capacity": {"capex", "utilisation"}, "margins": {"ebitda_margin", "ebit_margin", "gross_margin", "pat_margin"}, "revenue": {"revenue", "revenue_growth_cc"},
                      "debt": {"net_debt"}, "asset_quality": {"credit_cost", "gnpa"}, "cash": {"wc_days"}, "profit": {"pat", "ebitda"}}
        want = set().union(*[metric_for.get(t, set()) for t in topics]) if topics != ["guidance"] else None
        es = [e for e in self.ledger if e["kind"] == "guidance" and (want is None or e["metric"] in want or (e.get("segment") and "revenue" in (want or set())))]
        es.sort(key=lambda e: (P.sort_key(e.get("period") or ""), e["metric_label"]))
        for e in es:
            first = next((h for h in e["history"] if h.get("fact_id")), None)
            fdoc = self.docs.get(first["doc_id"]) if first else None
            where = (f"the {first['call']} call" if fdoc and fdoc["kind"] == "transcript" else f"the {fdoc['kind'].replace('_', ' ')} {first['call']}") if fdoc else None
            said_on = (f" (first stated on {where}" + (f" as {first['target']}" if first.get("target") and first["target"] != e.get("target") else "") + ")") if where else ""
            outcome = {"delivered": "delivered", "ahead": "ahead", "missed": "missed", "pending": f"still open ({e.get('status_note') or 'pending'})",
                       "dropped": f"dropped ({e.get('status_note')})", "unverifiable": "not checkable from the statements"}.get(e["verdict"], e["verdict"])
            tgt = e.get("target") or "no number given"
            text = f"{e['metric_label']} for {e.get('period')}: {tgt}{said_on}. Outcome: {outcome}."
            if e.get("actual_fact"):
                text += f" Reported: {self.disp(e['actual_fact'])}."
            a.add("guidance", text, [h["fact_id"] for h in e["history"] if h.get("fact_id")][:4] + ([e["actual_fact"]] if e.get("actual_fact") else []), info="guidance",
                  verdict=e["verdict"], explicit=e["explicit"])
        terms = " ".join(TOPICS[t]["terms"] for t in topics)
        ledger_quotes = {self.f[h["fact_id"]]["quote"] for e in es for h in e["history"] if h.get("fact_id") and self.f.get(h["fact_id"], {}).get("quote")}
        extra = [pid for pid in self.search(a, terms, future=True, k=6, min_score=1.0)
                 if not any(q_[:60] in a.passages[pid]["text"] for q_ in ledger_quotes)]
        if extra:
            a.add("management", "Other forward-looking statements on this, not tracked as numeric targets:", extra[:4], info="outlook")
        if not es and not extra:
            a.add("gap", f"The documents read contain no statement by management about {', '.join(topics).replace('_', ' ')} for a future period.", [])
            return
        closed = [e for e in es if e["verdict"] in ("delivered", "ahead", "missed") and e["explicit"]]
        if closed:
            kept = sum(e["verdict"] != "missed" for e in closed)
            a.add("interpretation", f"Of the {len(closed)} explicit target{'s' if len(closed) > 1 else ''} here whose period has closed, {kept} {'was' if kept == 1 else 'were'} kept.",
                  [e["actual_fact"] for e in closed if e.get("actual_fact")])

    def contradictions(self, a: Answer, q: str) -> None:
        rules = ("commentary_vs_numbers", "assertion_contradicted", "documents_disagree", "guidance_missed", "guidance_dropped")
        ds = [d for d in self.r["sections"]["nvn"]["discrepancies"] if d["rule"] in rules]
        ds = [d for d in ds if d["rule"] != "guidance_dropped" or d["severity"] >= 3]
        if not ds:
            a.add("note", "None of the contradiction tests fired on the documents read: no upbeat commentary next to falling figures, no quoted figure the statements contradict, "
                  "no two documents disagreeing on a target.", [])
            return
        order = {"commentary_vs_numbers": 0, "assertion_contradicted": 1, "documents_disagree": 2, "guidance_missed": 3, "guidance_dropped": 4}
        for d in sorted(ds, key=lambda d: (order[d["rule"]], -d["severity"])):
            a.add("finding", d["text"], d["evidence"], info="computed", rule=d["rule"], implication=d.get("implication"))
        a.add("interpretation", "Each item pairs something management said with a figure from the filed statements; the implication under each is FINN's reading, not management's.",
              [x for d in ds[:2] for x in d["evidence"]])

    def said_about(self, a: Answer, q: str) -> None:
        """A theme across calls: what management said, call by call, with the tone FINN read and any shift."""
        themes = set().union(*[TOPICS[t]["themes"] for t in a.topics]) if a.topics else set()
        if not themes:
            return self.lookup(a, q)
        calls = {d["id"]: d for d in self.calls()}
        by_call: dict[str, list[dict]] = defaultdict(list)
        for c in self.claims:
            if c["doc_id"] in calls and c.get("theme") in themes and c.get("fact_id"):
                by_call[c["doc_id"]].append(c)
        order = sorted(by_call, key=lambda d: P.q_index(calls[d]["period"]))
        if not order:
            return self.lookup(a, q)
        for d in order:
            cs = by_call[d]
            tones = Counter(c["tone"] for c in cs)
            t = "positive" if tones["positive"] > tones["negative"] else "negative" if tones["negative"] > tones["positive"] else "mixed or neutral"
            a.add("management", f"{calls[d]['period']} call ({t}):", [c["fact_id"] for c in cs[:3]], info="assertion")
        shifts = [s_ for s_ in self.r["sections"]["nvn"]["shifts"] if s_["theme"] in themes]
        for s_ in shifts:
            a.add("interpretation", s_["detail"] + " Tone is FINN's word-list reading of the quotes above.", s_["evidence"])
        missing = [d["period"] for d in self.calls() if d["id"] not in by_call]
        if missing:
            a.add("note", f"Not discussed in the {', '.join(missing)} call transcripts read.", [])
        # The theme is broad ("margins"); when the question names something specific ("fuel and power costs"),
        # show the passages that mention it too.
        topic_words = set(toks(" ".join(TOPICS[t]["terms"] for t in a.topics))) | set(toks("say said management about talk comment discuss call"))
        specific = [t for t in toks(q) if t not in topic_words]
        if specific:
            pids = self.search(a, " ".join(specific), k=3, min_score=1.0)
            if pids:
                a.add("management", f"Passages that mention {' '.join(w for w in re.findall(r'[A-Za-z]+', q) if _stem(w.lower()) in specific)}:", pids)

    def trend(self, a: Answer, q: str) -> None:
        if "asset_quality" in a.topics and self.fin:
            ids = [fid for fid in self.f if re.fullmatch(r"c:(FY\d{2}|H1FY\d{2}):credit_cost", fid)]
            ids.sort(key=lambda fid: P.sort_key(self.f[fid]["period"]))
            if ids:
                a.add("fact", "Credit cost (impairment on loans, annualised, on average on-book loans): " + "; ".join(f"{self.f[i]['period']} {self.f[i]['display']}" for i in ids) + ".", ids, info="computed")
            return self.said_about(a, q)
        if not any(t in a.topics for t in ("margins", "revenue", "profit")) and any(TOPICS[t]["themes"] for t in a.topics):
            return self.said_about(a, q)
        t = self.r["sections"]["trajectory"]
        num, label = self.margin_key()
        key = {"margins": f"{num}_margin" if not self.fin else "nii", "revenue": "revenue", "profit": "pat"}.get(next((x for x in a.topics if x in ("margins", "revenue", "profit")), "revenue"))
        ser = t["series"].get(key if key != "ebit_margin" else "ebitda_margin") or []
        if key == "ebit_margin":
            ser = [f"c:{qq.replace(' ', '')}:ebit_margin" if f"c:{qq.replace(' ', '')}:ebit_margin" in self.f else None for qq in t["quarters"]]
        pts = [(qq, fid) for qq, fid in zip(t["quarters"], ser) if fid]
        if not pts:
            return self.lookup(a, q)
        a.add("fact", f"By quarter: " + "; ".join(f"{qq} {self.f[fid]['display']}" for qq, fid in pts) + ".", [fid for _, fid in pts], info="computed")
        ann = [x for x in t["annual"] if x.get("revenue")]
        if ann and key == "revenue":
            a.add("fact", "By year: " + "; ".join(f"{x['period']} {self.f[x['revenue']]['display']}" + (f" ({self.f[x['revenue_growth']]['display']})" if x.get("revenue_growth") else "") for x in ann) + ".",
                  [x["revenue"] for x in ann] + [x["revenue_growth"] for x in ann if x.get("revenue_growth")], info="reported")

    def lookup(self, a: Answer, q: str) -> None:
        terms = " ".join(TOPICS[t]["terms"] for t in a.topics) + " " + q
        pids = self.search(a, terms, k=4, min_score=2.0)
        tables = self.search(a, q, roles=("company",), kinds={"results"}, k=1, min_score=3.0)
        if pids:
            a.add("management", "Passages in the documents that match the question:", pids)
        if tables:
            a.add("table", "Statement page that matches the question:", tables)
        if pids or tables:
            a.add("gap", "FINN has no computed analysis for this question; the passages above are what the documents say. Open them to read the context.", [])


# ------------------------------------------------------------------ validation


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _nums(s: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(s)}


def evidence_text(cid: str, report: dict, passages: dict[str, dict]) -> str:
    f = report["facts"].get(cid)
    if f:
        return " ".join(str(f.get(k) or "") for k in ("label", "display", "quote", "row_text", "formula", "period", "note"))
    p = passages.get(cid)
    return (p["text"] + " " + (p.get("section") or "") + " " + (p.get("period") or "")) if p else ""


def validate(block: dict, report: dict, passages: dict[str, dict], question: str, strict: bool) -> str | None:
    """None if the block is supported; otherwise the reason it isn't."""
    if block["kind"] == "gap" or block["kind"] == "note" and not block["cites"]:
        return None
    if not block["cites"]:
        return "no citation" if block["kind"] not in ("fact",) or strict else None
    missing = [c for c in block["cites"] if c not in report["facts"] and c not in passages]
    if missing:
        return f"cites unknown evidence {missing[:2]}"
    # The question is not evidence: a number or claim the user typed must not validate an answer.
    ev = " ".join(evidence_text(c, report, passages) for c in block["cites"])
    # Period labels and small counts written by FINN's own templates are allowed in rule mode.
    text = re.sub(r"\b(?:Q[1-4]|H[12]|9M)\s?FY\d{2}\b|\bFY\d{2}\b", "", block["text"])
    stray = [n for n in _nums(text) if n not in _nums(ev) and not (not strict and re.fullmatch(r"\d{1,2}", n))]
    if stray:
        return f"numbers not in the cited evidence: {stray[:4]}"
    if strict:
        from ..explain import _CAUSAL
        cause = next((m.group(0) for m in _CAUSAL.finditer(text) if m.group(0).lower() not in ev.lower()), None)
        if cause:
            return f"states a cause ({cause!r}) the cited evidence doesn't"
        words = [w for w in toks(text) if len(w) > 3]
        evw = set(toks(ev))
        if words:
            share = sum(w in evw for w in words) / len(words)
            if share < (0.35 if block["kind"] == "interpretation" else 0.5):
                return f"only {share:.0%} of its words appear in the cited evidence"
    return None


# ------------------------------------------------------------------ model synthesis (optional)


def model_answer(rules: dict, report: dict, passages: dict[str, dict], complete: Callable[[str], str], model: str) -> dict:
    """Let a model write the answer from the evidence pack; keep only blocks that pass validation."""
    pack = []
    for cid in dict.fromkeys(c for b in rules["blocks"] for c in b["cites"]):
        f = report["facts"].get(cid)
        if f:
            pack.append({"id": cid, "type": f["info_class"], "label": f["label"], "value": f.get("display"), "quote": f.get("quote")})
        elif cid in passages:
            p = passages[cid]
            pack.append({"id": cid, "type": "passage", "document": p["doc_kind"], "period": p.get("period"), "page": p["page"], "speaker": p.get("speaker"), "text": p["text"]})
    if not pack:
        return rules
    prompt = (
        "You answer an investor's question about one company using ONLY the evidence items below. You know nothing else about this company.\n"
        "Write 2-6 blocks. Each block is one or two sentences and must cite the ids of the evidence it uses. Use only numbers that appear in the cited items.\n"
        "kind is 'fact' for what the documents report, 'management' for what management said, 'interpretation' for your reading of the evidence.\n"
        "If the evidence doesn't answer the question, say so in a block of kind 'gap' with no citations.\n"
        'Reply as JSON: {"blocks": [{"kind": "...", "text": "...", "cite": ["id", ...]}]}\n'
        f"QUESTION: {rules['question']}\nEVIDENCE: {json.dumps(pack, ensure_ascii=False)}"
    )
    try:
        raw = complete(prompt)
        m = re.search(r"\{.*\}", raw, re.S)
        blocks = json.loads(m.group(0) if m else raw)["blocks"]
    except Exception as e:  # noqa: BLE001
        return {**rules, "model_rejected": f"unparseable model output ({type(e).__name__})"}
    kept, dropped = [], []
    for b in blocks:
        blk = {"kind": str(b.get("kind", "")), "text": str(b.get("text", "")).strip(), "cites": [str(x) for x in b.get("cite", [])]}
        if blk["kind"] not in ("fact", "management", "interpretation", "gap") or not blk["text"]:
            dropped.append("malformed block")
            continue
        why = validate(blk, report, passages, rules["question"], strict=True)
        if why:
            dropped.append(why)
            continue
        kept.append({**blk, "info": "generated" if blk["kind"] == "interpretation" else None})
    if not any(b["kind"] in ("fact", "management") for b in kept):
        return {**rules, "model_rejected": "; ".join(dropped[:3]) or "no supported block"}
    return {**rules, "blocks": kept, "method": f"model ({model}), every block checked against its citations", "dropped_blocks": dropped,
            "rules_blocks": rules["blocks"]}


# ------------------------------------------------------------------ entry point


def answer(question: str, report: dict, passages: list[dict], complete: Callable[[str], str] | None = None, model: str = "", asker: "Asker | None" = None) -> dict:
    q = re.sub(r"\s+", " ", question).strip()[:500]
    sym = report["identity"]["symbol"]
    intent = intent_of(q)
    a = Answer(question=q, intent=intent, topics=topics_of(q))
    base = {"question": q, "symbol": sym, "dataset": report["dataset"], "as_of": report["as_of"]}
    if not q:
        return {**base, "intent": "empty", "status": "insufficient", "blocks": [], "passages": {}, "method": "rules"}
    if intent == "out_of_scope" or GENERAL.search(q):
        msg = ("FINN doesn't give recommendations, price targets or predictions. It can show what the company's filings say: try asking about guidance, margins, cash flow or what changed between calls."
               if intent == "out_of_scope" else "Ask FINN answers questions about this company from its own filings, and nothing else.")
        return {**base, "intent": "out_of_scope", "topics": a.topics, "status": "out_of_scope", "blocks": [{"kind": "note", "text": msg, "cites": []}], "passages": {}, "method": "rules"}
    ak = asker or Asker(report, passages)
    getattr(ak, intent)(a, q)
    # Validation, also for rule-written blocks: an unsupported block is dropped, not shown.
    kept, dropped = [], []
    for b in a.blocks:
        why = validate(b, report, a.passages, q, strict=False)
        (dropped if why else kept).append(b if not why else {**b, "reason": why})
    substantive = [b for b in kept if b["kind"] in ("fact", "management", "guidance", "finding", "table") and b["cites"]]
    gaps = [b for b in kept if b["kind"] == "gap"]
    if not substantive:
        status = "insufficient"
        if not gaps:
            kept.append({"kind": "gap", "cites": [], "text": f"The documents read for {sym} don't address this question. Searched: "
                         + f"{len(ak.calls())} call transcripts, {sum(1 for d in report['documents'] if d['kind'] == 'results' and d['status'] == 'parsed')} results filings, "
                         + f"{sum(1 for d in report['documents'] if d['kind'] in ('presentation', 'annual_report') and d['status'] == 'parsed')} presentations and annual reports."})
    else:
        status = "partial" if gaps else "answered"
    docs_used = sorted({(a.passages.get(c) or {}).get("doc_id") or (report["facts"].get(c) or {}).get("doc_id") for b in kept for c in b["cites"]} - {None})
    out = {**base, "intent": intent, "topics": a.topics, "status": status, "blocks": kept, "dropped": dropped, "notes": a.notes,
           "passages": a.passages, "documents": docs_used, "method": "rules"}
    if complete and status != "insufficient":
        out = model_answer(out, report, a.passages, complete, model)
    return out


def cost_lines(numbers, quarters: list[str], is_financial: bool) -> dict:
    """Operating cost lines as a share of revenue per quarter (computed facts), for margin questions."""
    if is_financial:
        return {}
    out: dict[str, dict] = {}
    keys = ["materials", "purchases", "inventory_change", "employee", "other_exp"]
    for q in quarters:
        rev = numbers.flow(q, "revenue")
        if not rev or not rev.value:
            continue
        lines = {}
        ex = [k for k in numbers.q.get(q, {}) if k.startswith("x:")]
        for k in keys + ex:
            v = numbers.flow(q, k)
            if not v:
                continue
            from .financials import FIELD_LABEL
            lab = FIELD_LABEL.get(k) or numbers.labels.get(k, k)
            share = numbers._computed(f"c:{q.replace(' ', '')}:share:{k}", f"{lab} as a share of revenue, {q}", round(v.value / rev.value, 4), "pct", q,
                                      f"{lab} ÷ revenue from operations", [v.fact, rev.fact])
            lines[k] = [lab, share.value, share.fact, {}]
        if lines:
            out[q] = lines
    # Changes in each line's share against the year-ago and previous quarter, as facts of their own.
    for q, lines in out.items():
        for base in (P.shift_year(q), P.prev_q(q)):
            for k, row in lines.items():
                b = out.get(base, {}).get(k)
                if not b:
                    continue
                chg = numbers._computed(f"c:{q.replace(' ', '')}:share_chg:{k}:{base.replace(' ', '')}", f"Change in {row[0].lower()} as a share of revenue, {base} to {q}",
                                        round((row[1] - b[1]) * 100, 2), "pp", q, f"share {q} - share {base}", [row[2], b[2]])
                row[3][base] = [chg.value, chg.fact]
    return out
