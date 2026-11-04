"""Narrative vs Numbers: the deterministic join between claims and actuals.

* Guidance claims are threaded by (metric, segment, period). Each later
  statement is classified as reiterated, raised, lowered, changed or
  withdrawn; a complete later transcript that doesn't mention an open
  thread marks it "not repeated".
* The latest stance on each thread gets a verdict against actuals from the
  numbers path: delivered / ahead / missed for closed periods, pending (on
  track / at risk, with the run-rate the rest of the period needs) for open
  ones, unverifiable when the metric isn't in the filed statements.
* Assertions about the past are checked on every plausible basis before
  being called contradicted.
* Narrative shifts compare management's tone on each theme across calls.

Nothing here calls a model. Every verdict can be recomputed from the facts.
"""

from __future__ import annotations

import hashlib

from . import periods as P
from .financials import Facts, Numbers, Val, fmt_val
from .metrics import BY_ID, Metric
from .models import Claim, Doc, Fact, HistoryItem, LedgerEntry, Point, Shift, Target

AMOUNT_KEY = {"revenue": "revenue", "ebitda": "ebitda", "pat": "pat"}
MARGIN_NUM = {"ebitda_margin": "ebitda", "ebit_margin": "ebit", "gross_margin": "gross_profit", "pat_margin": "pat"}


def claim_fact(facts: Facts, c: Claim, doc: Doc) -> str:
    label = {"guidance": "Guided", "assertion": "Management said", "outlook": "Commentary"}[c.kind]
    f = Fact(
        id=c.id, info_class=c.kind, label=f"{label}: {c.metric_label or c.theme or 'statement'}" + (f", {c.period}" if c.period and c.kind == "guidance" else ""),
        period=c.call_period, doc_id=c.doc_id, page=c.page, section=c.section, speaker=c.speaker, role=c.role, quote=c.quote,
        note=(c.target.reading if c.target else None) if c.kind != "outlook" else None,
    )
    if c.confirmed_analyst_figure and c.context_quote:
        f.note = (f.note + ". " if f.note else "") + f"Confirming the analyst's figure: \"{c.context_quote[:220]}\""
    c.fact_id = facts.add(f)
    return c.fact_id


def _tdisplay(t: Target | None, m: Metric) -> str | None:
    if not t:
        return None
    if t.kind == "direction":
        return {"up": "higher", "down": "lower", "flat": "flat"}[t.direction or "up"]
    if t.kind == "words":
        return f"“{t.text}”"
    u = "%" if t.unit == "pct" else " pp" if t.unit == "pp" else "x" if t.unit == "x" else " cr" if t.unit == "cr" else ""
    pre = "₹" if t.unit == "cr" else ""

    dec = max((len(f"{x:g}".split(".")[1]) if "." in f"{x:g}" else 0) for x in (t.low, t.high) if x is not None) if (t.low is not None or t.high is not None) else 0

    def v(x: float) -> str:
        return f"{x:+.{dec}f}" if t.unit == "pp" else f"{x:,.{dec}f}" if t.unit == "cr" else f"{x:.{dec}f}"
    if t.kind in ("range", "delta") and t.low is not None and t.high is not None and t.low != t.high:
        return f"{pre}{v(t.low)}–{v(t.high)}{u}"
    if t.kind == "floor":
        return f"≥ {pre}{v(t.low)}{u}"  # type: ignore[arg-type]
    if t.kind == "ceiling":
        return f"≤ {pre}{v(t.high)}{u}"  # type: ignore[arg-type]
    if t.kind == "point" and t.low is not None and t.high is not None:
        mid = round((t.low + t.high) / 2, 4)
        md = len(f"{mid:g}".split(".")[1]) if "." in f"{mid:g}" else 0
        ms = f"{mid:,.{md}f}" if t.unit == "cr" else f"{mid:.{md}f}"
        return f"~{pre}{ms}{u}" if t.low != t.high else f"{pre}{ms}{u}"
    if t.kind == "multiple":
        return f"{t.low:g}x"
    return t.text


def _interval(t: Target) -> tuple[float | None, float | None]:
    f = 0.01 if t.unit == "pct" else 1.0
    return (t.low * f if t.low is not None else None, t.high * f if t.high is not None else None)


def _ytd_label(n: Numbers, period: str) -> str | None:
    qs = P.quarters(period)
    have = [q for q in qs if q in n.q and "revenue" in n.q[q]]
    k = 0
    for q in qs:
        if q in have:
            k += 1
        else:
            break
    if k == 0:
        return None
    if k == len(qs):
        return period
    fy = P.parse(period)[1] if P.parse(period) else 0  # type: ignore[index]
    first = P.parse(qs[0])
    if first and first[0] == "Q1":
        return {1: f"Q1 FY{fy % 100:02d}", 2: f"H1 FY{fy % 100:02d}", 3: f"9M FY{fy % 100:02d}"}[k]
    return qs[0] if k == 1 else None


def _family(metric: str) -> str:
    return "revenue" if metric.startswith("revenue") else metric


def _sev(hedge: str | None, base: int) -> int:
    return max(0, base - 1) if hedge in ("aspirational", "conditional") else base


class Ledger:
    def __init__(self, facts: Facts, numbers: Numbers, docs: dict[str, Doc], is_financial: bool):
        self.facts, self.n, self.docs, self.fin = facts, numbers, docs, is_financial
        self.entries: list[LedgerEntry] = []
        self.shifts: list[Shift] = []
        self.claims: list[Claim] = []
        self.conflicts: list[dict] = []

    # ------------------------------------------------------------- actuals
    def growth_actual(self, period: str, m: Metric, segment: str | None) -> Val | None:
        if segment:
            return self.segment_growth(period, segment)
        key = AMOUNT_KEY.get(m.id)
        if m.id == "loan_growth":
            return self.n.loan_growth_ytd(period)
        return self.n.growth(period, key) if key else None

    def segment_growth(self, period: str, segment: str) -> Val | None:
        qs = P.quarters(period)
        cur = [self.n._reported(self.n.seg, q, segment, "seg") for q in qs]
        base = [self.n._reported(self.n.seg, P.shift_year(q), segment, "seg") for q in qs]
        if any(x is None for x in cur + base):
            return None
        a, b = sum(x.value for x in cur), sum(x.value for x in base)  # type: ignore[union-attr]
        return self.n._computed(f"c:{period.replace(' ', '')}:seg:{segment}:growth", f"{segment} revenue growth, {period}", a / b - 1, "growth", period,
                                f"segment revenue {period} ÷ same period last year - 1", [x.fact for x in cur + base])  # type: ignore[union-attr]

    def level_actual(self, period: str, m: Metric) -> Val | None:
        if m.id in MARGIN_NUM:
            return self.n.margin(period, MARGIN_NUM[m.id])
        if m.id == "nim":
            return self.n.nim(period)
        if m.id == "credit_cost":
            return self.n.credit_cost(period)
        return None

    def amount_actual(self, period: str, m: Metric) -> Val | None:
        if m.id == "capex":
            return self.n.capex(period)
        if m.id == "net_debt":
            return self.n.net_debt(period)
        if m.id == "wc_days":
            return self.n.wc_days(period)
        return None

    def actual(self, period: str, m: Metric, t: Target, segment: str | None) -> Val | None:
        if t.kind == "delta":
            base = t.base_period or f"FY{(P.parse(period)[1] - 1) % 100:02d}"  # type: ignore[index]
            num = MARGIN_NUM.get(m.id)
            return self.n.margin_change(period, base, num) if num else None
        if t.kind == "multiple":
            return None
        if t.kind == "direction" and m.kind == "level" and m.id in MARGIN_NUM:
            return self.n.margin_change(period, P.shift_year(period), MARGIN_NUM[m.id])
        if m.kind == "growth":
            return self.growth_actual(period, m, segment)
        if m.kind == "level":
            return self.level_actual(period, m)
        return self.amount_actual(period, m)

    # ------------------------------------------------------------- guidance
    def build_guidance(self, claims: list[Claim], complete_calls: list[Doc]) -> None:
        docs = self.docs
        order = {d.id: (d.filed_at.isoformat() if d.filed_at else "") for d in docs.values()}
        gs = sorted([c for c in claims if c.kind == "guidance"], key=lambda c: order.get(c.doc_id, ""))
        threads: dict[tuple, list[Claim]] = {}
        withdrawals = [c for c in gs if c.withdraws]
        for c in gs:
            if c.withdraws or not c.metric or not c.period:
                continue
            threads.setdefault((c.metric, c.segment, c.period), []).append(c)
        latest_q = self.n.latest()
        for (metric, segment, period), items in threads.items():
            m = BY_ID[metric]
            hist: list[HistoryItem] = []
            stance: Claim | None = None
            for c in items:
                t = c.target or (stance.target if stance else None)  # a reaffirmation carries the thread's target
                change = "first"
                if stance and c.target is not None and c.target.kind in ("direction", "words") and stance.target is not None and stance.target.kind not in ("direction", "words"):
                    # A numeric target restated only in words ("healthy growth"): the number wasn't repeated.
                    hist.append(HistoryItem(call=docs[c.doc_id].period, doc_id=c.doc_id, claim_id=c.id, change="softened", target=_tdisplay(stance.target, m), fact_id=c.fact_id))
                    continue
                prev_item = next((h for h in reversed(hist) if h.claim_id), None)
                if stance and prev_item and docs[c.doc_id].period == prev_item.call and docs[c.doc_id].kind != docs[prev_item.doc_id].kind and (c.target is None or _interval(c.target) == _interval(stance.target) if stance.target else False):
                    # The same statement in the presentation and on the call for one quarter is one statement.
                    hist.append(HistoryItem(call=docs[c.doc_id].period, doc_id=c.doc_id, claim_id=c.id, change="also stated", target=_tdisplay(t, m), fact_id=c.fact_id))
                    continue
                if (stance and prev_item and docs[c.doc_id].period == prev_item.call and docs[c.doc_id].kind != docs[prev_item.doc_id].kind
                        and c.target is not None and c.target.kind not in ("direction", "words") and stance.target is not None
                        and stance.target.kind not in ("direction", "words") and _interval(c.target) != _interval(stance.target)):
                    # Two documents for the same quarter state different targets: a contradiction, not a revision.
                    hist.append(HistoryItem(call=docs[c.doc_id].period, doc_id=c.doc_id, claim_id=c.id, change="differs", target=_tdisplay(c.target, m), fact_id=c.fact_id))
                    self.conflicts.append({"metric": metric, "metric_label": m.label + (f" ({segment})" if segment else ""), "period": period, "call": docs[c.doc_id].period,
                                           "first": prev_item.fact_id, "second": c.fact_id, "first_target": prev_item.target, "second_target": _tdisplay(c.target, m),
                                           "first_doc": docs[prev_item.doc_id].kind, "second_doc": docs[c.doc_id].kind})
                    stance = c
                    continue
                if stance:
                    a, b = _interval(stance.target) if stance.target else (None, None), _interval(t) if t else (None, None)
                    if c.target is None or a == b and c.target.kind == (stance.target.kind if stance.target else None):
                        change = "reiterated"
                    elif stance.target is None or stance.target.kind in ("direction", "words"):
                        change = "changed"  # first stated as words or a direction, now quantified
                    elif (b[0] if b[0] is not None else -1e18) >= (a[0] if a[0] is not None else -1e18) and (b[1] if b[1] is not None else 1e18) >= (a[1] if a[1] is not None else 1e18):
                        change = "raised"
                    elif (b[0] if b[0] is not None else -1e18) <= (a[0] if a[0] is not None else -1e18) and (b[1] if b[1] is not None else 1e18) <= (a[1] if a[1] is not None else 1e18):
                        change = "lowered"
                    else:
                        change = "changed"
                hist.append(HistoryItem(call=docs[c.doc_id].period, doc_id=c.doc_id, claim_id=c.id, change=change, target=_tdisplay(t, m), fact_id=c.fact_id))
                if c.target is not None or stance is None:
                    stance = c
            assert stance is not None
            self._annotate(hist, items, docs)
            target = stance.target if stance.target else None
            last_doc = docs[items[-1].doc_id]
            end = P.end_of(period)
            # A withdrawal only touches periods still open when it was made.
            withdrawn = next((w for w in withdrawals if (w.metric is None or _family(w.metric) == _family(metric)) and order.get(w.doc_id, "") > order.get(last_doc.id, "")
                              and not (end and docs[w.doc_id].filed_at and docs[w.doc_id].filed_at.date() > end)), None)
            if withdrawn:
                hist.append(HistoryItem(call=docs[withdrawn.doc_id].period, doc_id=withdrawn.doc_id, claim_id=withdrawn.id, change="withdrawn", fact_id=withdrawn.fact_id))
            else:
                for d in complete_calls:
                    if order.get(d.id, "") <= order.get(last_doc.id, "") or d.kind != "transcript":
                        continue
                    if end and d.filed_at and d.filed_at.date() > end:
                        continue  # period already over when this call happened
                    if any(c.doc_id == d.id for c in items):
                        continue
                    hist.append(HistoryItem(call=d.period, doc_id=d.id, claim_id=None, change="not repeated"))
            e = self.verdict(metric, segment, period, target, stance, hist, latest_q)
            e.better = m.better
            self._annotate(e.history, items, docs)
            e.evidence = [h.fact_id for h in hist if h.fact_id]
            if e.actual_fact:
                e.evidence.append(e.actual_fact)
            if e.required_fact:
                e.evidence.append(e.required_fact)
            self.entries.append(e)

    def _annotate(self, hist: list[HistoryItem], items: list[Claim], docs: dict[str, Doc]) -> None:
        """Dates and numeric bands on each history step, for the credibility timeline."""
        by_id = {c.id: c for c in items}
        band: dict | None = None
        for h in hist:
            d = docs.get(h.doc_id)
            if d:
                h.date = (d.parse.get("call_date") if d.kind == "transcript" else None) or (d.filed_at.date().isoformat() if d.filed_at else None)
            c = by_id.get(h.claim_id or "")
            if h.change in ("not repeated", "withdrawn", "softened"):
                h.band = None
                band = None if h.change != "not repeated" else band
                continue
            if c and c.target and c.target.kind not in ("direction", "words"):
                band = {"kind": c.target.kind, "low": c.target.low, "high": c.target.high, "unit": c.target.unit}
            elif c and c.target and c.target.kind in ("direction", "words"):
                band = None
            h.band = band

    def verdict(self, metric: str, segment: str | None, period: str, t: Target | None, stance: Claim, hist: list[HistoryItem], latest_q: str | None) -> LedgerEntry:
        m = BY_ID[metric]
        eid = "lg:" + hashlib.sha1(f"{metric}|{segment}|{period}".encode()).hexdigest()[:10]
        label = m.label + (f" ({segment})" if segment else "")
        base = dict(id=eid, kind="guidance", metric=metric, metric_label=label, segment=segment, period=period, target=_tdisplay(t, m),
                    reading=t.reading if t else None, hedge=stance.hedge, history=hist,
                    explicit=bool(t and t.kind not in ("direction", "words")), target_kind=t.kind if t else None)
        stance_fact = stance.fact_id
        horizon_note = ""
        if any(h.change == "withdrawn" for h in hist):
            w = next(h for h in hist if h.change == "withdrawn")
            ytd = _ytd_label(self.n, period) if t and t.kind not in ("words", "multiple") else None
            a = self.actual(ytd, m, t, segment) if ytd and t and not m.unverifiable else None
            ctx, sev = "", 2
            if a and t:
                lo, hi = _interval(t) if t.kind != "delta" else (t.low, t.high)
                behind = (m.better == "up" and lo is not None and a.value < lo) or (m.better == "down" and hi is not None and a.value > hi)
                ctx = f" At that point {ytd} stood at {self.facts.items[a.fact].display} against {base['target']}" + (", outside the range." if behind else ".")
                sev = 3 if behind else 2
            return LedgerEntry(**base, verdict="dropped", status_note="withdrawn" + ("; behind" if sev == 3 else ""), detail=f"Management withdrew this guidance on the {w.call} call.{ctx}",
                               severity=_sev(stance.hedge, sev), actual_fact=a.fact if a else None)
        if m.unverifiable:
            return LedgerEntry(**base, verdict="unverifiable", detail=m.unverifiable, severity=0)
        if t is None or t.kind == "multiple":
            why = "The statement is a multi-year multiple; FINN checks it once the target year is reported." if t else "No target to check."
            return LedgerEntry(**base, verdict="pending" if t else "unverifiable", status_note="long horizon" if t else None, detail=why, severity=0)
        closed = latest_q is not None and all(q in self.n.q for q in P.quarters(period))
        if t.kind == "words":
            ref = period if closed else _ytd_label(self.n, period)
            a = self.words_actual(ref, m, segment) if ref else None
            ctx = f" {ref} actual for context: {self.facts.items[a.fact].display}." if a else ""
            return LedgerEntry(**base, verdict="unverifiable", status_note="words only", actual_fact=a.fact if a else None, severity=0,
                               detail=f"Management gave no number ({t.text!r}), so FINN doesn't score this.{ctx}")
        not_repeated = [h for h in hist if h.change in ("not repeated", "softened") and not any(x.change in ("reiterated", "raised", "lowered", "changed") and hist.index(x) > hist.index(h) for x in hist)]
        lowered = any(h.change == "lowered" for h in hist)
        if closed:
            a = self.actual(period, m, t, segment)
            if not a:
                return LedgerEntry(**base, verdict="unverifiable", detail=self._missing(period, m), severity=0)
            return self._closed({**base, "_stance_fact": stance_fact}, m, t, a, period, stance.hedge)
        ytd = _ytd_label(self.n, period)
        if not ytd:
            note = f"{period} hasn't started in the reported numbers yet (latest reported quarter: {latest_q})." if latest_q else "No reported quarters yet."
            e = LedgerEntry(**base, verdict="pending", status_note="not started", detail=note + horizon_note, severity=0)
        else:
            e = self._pending(base, m, t, period, ytd, segment, stance.hedge)
        if not_repeated:
            behind = e.status_note == "at risk"
            calls = ", ".join(h.call or "a later call" for h in not_repeated)
            soft = any(h.change == "softened" for h in not_repeated)
            e.verdict = "dropped"
            e.detail = (f"The number wasn't repeated on the {calls} call; management described it only in words. " if soft else
                        f"Not repeated on the {calls} call{'s' if len(not_repeated) > 1 else ''}. ") + e.detail
            e.severity = _sev(stance.hedge, 3 if behind else 1)
            e.status_note = "not repeated" + ("; behind" if behind else "")
        if lowered:
            e.severity = max(e.severity, 2)
        return e

    def words_actual(self, period: str, m: Metric, segment: str | None) -> Val | None:
        if m.kind == "growth":
            return self.growth_actual(period, m, segment)
        if m.kind == "level":
            return self.level_actual(period, m)
        return self.amount_actual(period, m)

    def _missing(self, period: str, m: Metric) -> str:
        if m.kind == "amount" and m.id == "capex":
            return f"No cash flow statement covering {period} was found in the filings read."
        if m.id in ("nim", "credit_cost", "loan_growth"):
            return f"Loans or impairment for {period} aren't available from the balance sheets read."
        return f"The {period} figures needed aren't in the filings read."

    def _closed(self, base: dict, m: Metric, t: Target, a: Val, period: str, hedge: str | None) -> LedgerEntry:
        stance_fact = base.pop("_stance_fact", None)
        lo, hi = _interval(t) if t.kind != "delta" else (t.low, t.high)
        v = a.value
        if t.kind == "direction":
            ok = (v > 0) if t.direction == "up" else (v < 0) if t.direction == "down" else abs(v) <= 0.01
            disp = self.facts.items[a.fact].display
            return LedgerEntry(**base, verdict="delivered" if ok else "missed", detail=f"{period} actual {disp}; guidance was directional only.", severity=0 if ok else _sev(hedge, 2), actual_fact=a.fact)
        tol = (m.tol / 100) if m.kind in ("growth", "level") and t.kind != "delta" else (m.tol if t.kind == "delta" else m.tol * (hi or lo or 0))
        if t.kind == "point" and t.low != t.high:
            tol = 0.0  # "around X" already carries its band; no second tolerance on top
        disp = self.facts.items[a.fact].display
        inside = (lo is None or v >= lo - tol) and (hi is None or v <= hi + tol)
        if inside:
            return LedgerEntry(**base, verdict="delivered", detail=f"{period} actual {disp} against {base['target']}.", actual_fact=a.fact, severity=0)
        above = hi is not None and v > hi + tol
        good = above if m.better == "up" else not above
        edge = hi if above else lo
        assert edge is not None
        pct = m.kind in ("growth", "level") and t.kind != "delta"
        unit = "pp" if pct or t.kind == "delta" else "cr"
        gap_v = round((v - edge) * 100, 2) if pct else round(v - edge, 2)
        edge_s = f"{edge * 100:g}%" if pct else f"{edge:+g} pp" if t.kind == "delta" else f"₹{edge:,.0f} cr"
        g = self.n._computed(f"c:gap:{base['id']}", f"Gap to the nearest edge of the target, {period}", gap_v, unit, period,
                             f"actual - {'upper' if above else 'lower'} edge of the target ({edge_s})" + ("; the edge is FINN's reading of an approximate figure" if t.kind == "point" and t.low != t.high else ""),
                             [a.fact] + ([stance_fact] if stance_fact else []))
        return LedgerEntry(**base, verdict="ahead" if good else "missed",
                           detail=f"{period} actual {disp} against {base['target']}: {self.facts.items[g.fact].display} from the {'upper' if above else 'lower'} edge ({edge_s}).",
                           actual_fact=a.fact, required_fact=g.fact, severity=0 if good else _sev(hedge, 3))

    def _pending(self, base: dict, m: Metric, t: Target, period: str, ytd: str, segment: str | None, hedge: str | None) -> LedgerEntry:
        a = self.actual(ytd, m, t, segment)
        if not a:
            return LedgerEntry(**base, verdict="pending", detail=f"{period} is still open; {self._missing(ytd, m)}", severity=0)
        disp = self.facts.items[a.fact].display
        lo, hi = _interval(t) if t.kind != "delta" else (t.low, t.high)
        req = self.required(period, ytd, m, t)
        note, sev, extra = "on track", 0, ""
        if t.kind == "direction":
            ok = a.value > 0 if t.direction == "up" else a.value < 0 if t.direction == "down" else True
            note = "on track" if ok else "at risk"
        elif m.better == "up" and lo is not None:
            tol = m.tol / 100 if m.kind in ("growth", "level") and t.kind != "delta" else m.tol if t.kind == "delta" else 0
            if m.kind == "amount":
                # Straight-line: the elapsed share of the period, less the metric's own tolerance.
                # (Spending is often back-ended; the "rest of the year needs" line below shows how much.)
                share = len(P.quarters(ytd)) / len(P.quarters(period))
                note = "on track" if a.value >= lo * share * (1 - m.tol) else "at risk"
                extra = f" Judged pro rata to the {len(P.quarters(ytd))} of {len(P.quarters(period))} quarters elapsed."
            else:
                note = "on track" if a.value >= lo - tol else "at risk"
        elif m.better == "down" and hi is not None:
            slack = m.tol * abs(hi) if m.kind == "amount" else m.tol / 100
            note = "on track" if a.value <= hi + slack else "at risk"
        if req:
            rf = self.facts.items[req[0].fact]
            extra += f" The rest of {period} needs {rf.display}" + (f", above the best quarter in the data ({self.facts.items[req[1].fact].display})" if req[1] and req[0].value > req[1].value else "") + "."
            if req[1] and req[0].value > req[1].value:
                note = "at risk"
        if note == "at risk":
            sev = _sev(hedge, 2)
        e = LedgerEntry(**base, verdict="pending", status_note=note, detail=f"{period} is still open. {ytd} actual {disp} against {base['target']}.{extra}",
                        actual_fact=a.fact, required_fact=req[0].fact if req else None, severity=sev)
        return e

    def required(self, period: str, ytd: str, m: Metric, t: Target) -> tuple[Val, Val | None] | None:
        """What the remaining quarters must deliver to reach the low end of the target."""
        qs = P.quarters(period)
        done = P.quarters(ytd)
        rest = [q for q in qs if q not in done]
        if not rest or t.kind in ("direction", "multiple"):
            return None
        lo, hi = _interval(t) if t.kind != "delta" else (t.low, t.high)
        pid = period.replace(" ", "")
        if m.kind == "growth" and m.id in AMOUNT_KEY and lo is not None:
            key = AMOUNT_KEY[m.id]
            cur = [self.n.metric_amount(q, key) for q in done]
            prior = [self.n.metric_amount(P.shift_year(q), key) for q in qs]
            if any(x is None for x in cur + prior):
                return None
            need_total = sum(x.value for x in prior) * (1 + lo)  # type: ignore[union-attr]
            rest_base = sum(x.value for x, q in zip(prior, qs) if q in rest)  # type: ignore[union-attr]
            r = (need_total - sum(x.value for x in cur)) / rest_base - 1  # type: ignore[union-attr]
            v = self.n._computed(f"c:req:{pid}:{m.id}", f"Growth the rest of {period} needs ({', '.join(rest)})", r, "growth", period,
                                 f"(same period last year × (1 + {lo * 100:g}%) - {ytd} actual) ÷ last year's {', '.join(rest)} - 1",
                                 [x.fact for x in cur + prior])  # type: ignore[union-attr]
            return v, None
        if m.kind == "level" and m.id in MARGIN_NUM and lo is not None and t.kind != "delta":
            num = MARGIN_NUM[m.id]
            ycur, yrev = self.n.metric_amount(ytd, num), self.n.flow(ytd, "revenue")
            g = self.n.growth(ytd, "revenue")
            rest_prior = [self.n.flow(P.shift_year(q), "revenue") for q in rest]
            if not (ycur and yrev and g) or any(x is None for x in rest_prior):
                return None
            rest_rev = sum(x.value for x in rest_prior) * (1 + g.value)  # type: ignore[union-attr]
            r = (lo * (yrev.value + rest_rev) - ycur.value) / rest_rev
            v = self.n._computed(f"c:req:{pid}:{m.id}", f"{m.label} the rest of {period} needs", r, "pct", period,
                                 f"({lo * 100:g}% × full-year revenue - {ytd} {num}) ÷ remaining revenue; remaining revenue assumed to grow at the {ytd} rate on last year's {', '.join(rest)}",
                                 [ycur.fact, yrev.fact, g.fact] + [x.fact for x in rest_prior])  # type: ignore[union-attr]
            margins = [self.n.margin(q, num) for q in self.n.quarters()]
            best = max((x for x in margins if x), key=lambda x: x.value, default=None)
            if best:
                best = self.n._computed(f"c:best:{m.id}", f"Best quarterly {m.label.lower()} in the data", best.value, "pct", self.facts.items[best.fact].period,
                                        f"maximum over {len(margins)} reported quarters", [x.fact for x in margins if x])
            return v, best
        if m.id == "capex" and lo is not None:
            a = self.n.capex(ytd)
            if not a:
                return None
            r = lo - a.value
            v = self.n._computed(f"c:req:{pid}:capex", f"Capex the rest of {period} needs", round(r, 1), "cr", period, f"{lo:g} cr target - {ytd} capex", [a.fact])
            return v, None
        return None

    # ------------------------------------------------------------- assertions
    def build_assertions(self, claims: list[Claim]) -> None:
        for c in claims:
            if c.kind != "assertion" or not c.metric:
                continue
            m = BY_ID[c.metric]
            eid = "as:" + c.id[3:]
            base = dict(id=eid, kind="assertion", metric=m.id, metric_label=m.label + (f" ({c.segment})" if c.segment else ""), segment=c.segment,
                        period=c.period, target=_tdisplay(c.target, m) if c.target else None, reading=c.target.reading if c.target else None, evidence=[c.fact_id] if c.fact_id else [])
            if m.unverifiable:
                self.entries.append(LedgerEntry(**base, verdict="unverifiable", detail=m.unverifiable))
                continue
            if not c.period or not P.parse(c.period):
                self.entries.append(LedgerEntry(**base, verdict="unverifiable", detail="The period this statement describes couldn't be pinned down."))
                continue
            checks = self._assert_values(c, m)
            if not checks:
                self.entries.append(LedgerEntry(**base, verdict="unverifiable", detail=f"The {c.period} figures needed to check this aren't in the filings read."))
                continue
            d = None if c.target else _dir(c.quote)
            results = []
            for basis, val in checks:
                if c.target and c.target.kind != "direction":
                    stated = (c.target.low + c.target.high) / 2 if c.target.low is not None and c.target.high is not None else (c.target.low if c.target.low is not None else c.target.high)
                    actual = val.value * 100 if self.facts.items[val.fact].unit in ("growth", "pct") else val.value
                    ok = stated is not None and abs(actual - stated) <= (0.35 if c.target.unit in ("pct", "pp") else abs(stated) * 0.02 + 0.5)
                else:
                    ok = (val.value > 0) if d == "up" else (val.value < 0) if d == "down" else abs(val.value) <= (0.5 if self.facts.items[val.fact].unit == "pp" else 0.01)
                results.append((basis, val, ok))
            oks = [r for r in results if r[2]]
            shown = "; ".join(f"{b}: {self.facts.items[v.fact].display}" for b, v, _ in results)
            if len(oks) == len(results):
                verdict, sev = "consistent", 0
            elif oks:
                verdict, sev = "partial", 1
            else:
                verdict, sev = "contradicted", 2 if c.doc_kind == "transcript" else 1
            e = LedgerEntry(**base, verdict=verdict, detail=f"Checked against reported figures ({shown}).", severity=sev, actual_fact=results[0][1].fact)
            e.evidence += [v.fact for _, v, _ in results]
            self.entries.append(e)

    def _assert_values(self, c: Claim, m: Metric) -> list[tuple[str, Val]]:
        per = c.period  # type: ignore[assignment]
        bases = [c.basis_hint] if c.basis_hint else (["yoy", "qoq"] if len(P.quarters(per)) == 1 else ["yoy"])
        out: list[tuple[str, Val]] = []
        for b in bases:
            ref = P.prev_q(per) if b == "qoq" else P.shift_year(per)
            if m.id == "loan_growth":
                v = self.n.loan_growth_ytd(per) if b == bases[0] else None
            elif m.kind == "growth":
                if c.segment:
                    v = self.segment_growth(per, c.segment) if b == "yoy" else None
                else:
                    key = AMOUNT_KEY.get(m.id)
                    v = self.n.growth(per, key, ref) if key else None
            elif m.kind == "level" and m.id in MARGIN_NUM:
                if c.target and c.target.kind == "point" and c.target.unit == "pct":
                    v = self.n.margin(per, MARGIN_NUM[m.id])
                    if v:
                        out.append(("level", v))
                    break
                v = self.n.margin_change(per, ref, MARGIN_NUM[m.id])
            elif m.id == "net_debt" and not c.target and self.n.bs_dates():
                # "We reduced debt": compare net debt at this balance-sheet date with the one before.
                end = P.end_of(per)
                asof = P.label_for_end(end, "ytd") if end else None
                dates = self.n.bs_dates()
                if asof in dates and dates.index(asof) > 0:
                    a, b = self.n.net_debt(dates[dates.index(asof) - 1]), self.n.net_debt(asof)
                    if a and b:
                        v = self.n._computed(f"c:bs:{asof.replace(' ', '')}:net_debt_chg", f"Change in net debt, {dates[dates.index(asof) - 1]} to {asof}", round(b.value - a.value, 2), "cr", asof,
                                             f"net debt {asof} - net debt {dates[dates.index(asof) - 1]}", [b.fact, a.fact])
                        out.append(("change", v))
                break
            elif m.id == "capex" and c.target and c.target.unit == "cr":
                v = self.n.capex(per)
                if v:
                    out.append(("amount", v))
                break
            elif m.id == "credit_cost":
                v = self.n.credit_cost(per)
            elif m.id == "loan_growth":
                v = self.n.loan_growth_ytd(per)
            else:
                v = None
            if v:
                out.append(("year on year" if b == "yoy" else "sequential", v))
        return out

    # ------------------------------------------------------------- narrative shifts
    def build_shifts(self, claims: list[Claim]) -> None:
        self.claims = claims
        calls = sorted({c.doc_id for c in claims if c.doc_kind == "transcript"}, key=lambda d: self.docs[d].filed_at.isoformat() if self.docs[d].filed_at else "")
        by_theme: dict[str, dict[str, list[Claim]]] = {}
        for c in claims:
            if c.doc_kind != "transcript" or not c.theme or c.tone == "neutral":
                continue
            by_theme.setdefault(c.theme, {}).setdefault(c.doc_id, []).append(c)
        for theme, per_call in by_theme.items():
            seq = [(d, per_call[d]) for d in calls if d in per_call]
            def tone(cs: list[Claim]) -> str:
                p = sum(1 for x in cs if x.tone == "positive")
                n = sum(1 for x in cs if x.tone == "negative")
                return "positive" if p > n else "negative" if n > p else "mixed"
            for (d1, c1), (d2, c2) in zip(seq, seq[1:]):
                t1, t2 = tone(c1), tone(c2)
                if t1 != t2 and "mixed" not in (t1, t2):
                    q1 = next(x for x in c1 if x.tone == t1)
                    q2 = next(x for x in c2 if x.tone == t2)
                    sid = "sh:" + hashlib.sha1(f"{theme}|{d1}|{d2}".encode()).hexdigest()[:10]
                    self.shifts.append(Shift(id=sid, theme=theme, from_call=self.docs[d1].period, to_call=self.docs[d2].period, from_tone=t1, to_tone=t2,
                                             detail=f"Management's tone on {theme.lower()} turned {t2} between the {self.docs[d1].period} and {self.docs[d2].period} calls.",
                                             evidence=[q1.fact_id, q2.fact_id]))  # type: ignore[list-item]
            if calls and seq and seq[0][0] == calls[-1] and len(calls) > 1 and tone(seq[0][1]) == "negative":
                q = next(x for x in seq[0][1] if x.tone == "negative")
                sid = "sh:" + hashlib.sha1(f"{theme}|new|{calls[-1]}".encode()).hexdigest()[:10]
                self.shifts.append(Shift(id=sid, theme=theme, from_call=None, to_call=self.docs[calls[-1]].period, from_tone="not mentioned", to_tone="negative",
                                         detail=f"{theme} came up as a concern on the {self.docs[calls[-1]].period} call without having been raised on the earlier calls read.",
                                         evidence=[q.fact_id]))  # type: ignore[list-item]


def _dir(quote: str) -> str | None:
    from .claims import direction
    return direction(quote)


# ------------------------------------------------------------------ discrepancies

def discrepancies(lg: Ledger) -> list[Point]:
    """Where the story and the numbers part ways, with what it implies."""
    f = lg.facts.items
    out: list[Point] = []
    for e in sorted(lg.entries, key=lambda e: -e.severity):
        ev = [x for x in e.evidence if x]
        if e.kind == "assertion" and e.verdict == "contradicted":
            out.append(Point(id="d:" + e.id, rule="assertion_contradicted", severity=e.severity, evidence=ev,
                             text=f"Management described {e.metric_label.lower()} in {e.period} in a way the reported figures don't support. {e.detail}",
                             implication="Treat management's characterisation of this quarter with caution; ask which basis they used."))
        elif e.kind == "guidance" and e.verdict == "missed":
            out.append(Point(id="d:" + e.id, rule="guidance_missed", severity=e.severity, evidence=ev,
                             text=f"{e.metric_label} guidance of {e.target} for {e.period} was missed. {e.detail}",
                             implication="A missed explicit target lowers the weight to put on the next one; check whether the miss was explained on the call that followed."))
        elif e.kind == "guidance" and e.verdict == "dropped":
            out.append(Point(id="d:" + e.id, rule="guidance_dropped", severity=e.severity, evidence=ev,
                             text=f"{e.metric_label} guidance of {e.target} for {e.period}: {e.detail}",
                             implication="Guidance that goes quiet while the numbers fall short usually precedes a reset; ask on the next call whether the target still stands."
                             if "behind" in (e.status_note or "") else "Silence isn't a miss, but the target should be confirmed before relying on it."))
        elif e.kind == "guidance" and e.verdict == "pending" and e.status_note == "at risk":
            out.append(Point(id="d:" + e.id, rule="guidance_at_risk", severity=e.severity, evidence=ev,
                             text=f"{e.metric_label} guidance of {e.target} for {e.period} is at risk. {e.detail}",
                             implication="If the year-to-date run-rate holds, the target will be missed; the size of the required step-up is the thing to test."))
        if e.kind == "guidance" and any(h.change == "lowered" for h in e.history):
            h = next(h for h in e.history if h.change == "lowered")
            prev = next((x for x in e.history if x.target and x.change != "lowered"), None)
            out.append(Point(id="r:" + e.id, rule="guidance_lowered", severity=2, evidence=[x.fact_id for x in e.history if x.fact_id],
                             text=f"{e.metric_label} guidance for {e.period} was lowered on the {h.call} call" + (f", from {prev.target} to {h.target}." if prev else "."),
                             implication="A lowered target is information in itself; compare the stated reason with the trend in the numbers."))
    out += commentary_vs_numbers(lg)
    for k in lg.conflicts:
        out.append(Point(id=f"dd:{k['metric']}:{k['period'].replace(' ', '')}:{k['call'].replace(' ', '')}", rule="documents_disagree", severity=2, evidence=[k["first"], k["second"]],
                         text=f"For {k['period']} {k['metric_label']}, the {k['call']} {k['first_doc'].replace('_', ' ')} said {k['first_target']} and the {k['second_doc'].replace('_', ' ')} said {k['second_target']}.",
                         implication="Two company documents for the same quarter disagree on the target. FINN tracks the later one; ask which the company stands by."))
    for s in lg.shifts:
        if s.to_tone == "negative":
            out.append(Point(id="d:" + s.id, rule="narrative_shift", severity=1, evidence=s.evidence, text=s.detail,
                             implication="A change in tone often leads the numbers by a quarter or two; watch the metrics this theme drives."))
    return out


DEMAND_THEMES = {"Demand", "Client spending", "Deal pipeline", "Pricing"}


def commentary_vs_numbers(lg: Ledger) -> list[Point]:
    """Upbeat words about the quarter just reported, next to numbers that went the other way.

    Only statements about the present or past are tested (a hopeful outlook isn't
    contradicted by today's numbers). Demand-type themes are tested against
    revenue growth year on year; margin commentary against the margin change.
    """
    from .claims import FUTURE
    out: list[Point] = []
    seen: set[tuple[str, str]] = set()
    for c in lg.claims:
        if c.doc_kind != "transcript" or c.tone != "positive" or not c.call_period or not c.fact_id or FUTURE.search(c.quote):
            continue
        q = c.call_period
        if not q.startswith("Q"):
            continue
        theme = c.theme or ""
        if theme in DEMAND_THEMES or (c.metric or "").startswith("revenue"):
            g = lg.n.growth(q, "revenue")
            if g and g.value < 0 and (q, "revenue") not in seen:
                seen.add((q, "revenue"))
                out.append(Point(id=f"cv:{q.replace(' ', '')}:revenue", rule="commentary_vs_numbers", severity=2, evidence=[c.fact_id, g.fact],
                                 text=f"On the {q} call management described {theme.lower() or 'the business'} positively, while reported revenue for {q} fell {lg.facts.items[g.fact].display.lstrip('-+')} year on year.",
                                 implication="Ask what the upbeat description refers to (orders, a segment, a month) and when it should show up in reported revenue."))
        elif theme == "Cash generation" and not lg.fin:
            per = {"Q2": "H1", "Q4": "FY"}.get(q[:2])
            if not per:
                continue
            ytd = f"{per} FY{q[-2:]}" if per == "H1" else f"FY{q[-2:]}"
            ocf, eb, fcf = lg.n.cf_val(ytd, "cfo"), lg.n.ebitda(ytd), lg.n.fcf(ytd)
            conv = lg.n.ratio(f"c:{ytd.replace(' ', '')}:cfo_ebitda", f"Cash conversion (OCF ÷ EBITDA), {ytd}", ocf, eb, "operating cash flow ÷ EBITDA", ytd)
            weak = [x for x in ((conv, conv and conv.value < 0.6, f"operating cash flow covered {lg.facts.items[conv.fact].display if conv else ''} of EBITDA"),
                                (fcf, fcf and fcf.value < 0, f"free cash flow was {lg.facts.items[fcf.fact].display if fcf else ''}")) if x[1]]
            if weak and (q, "cash") not in seen:
                seen.add((q, "cash"))
                out.append(Point(id=f"cv:{q.replace(' ', '')}:cash", rule="commentary_vs_numbers", severity=2, evidence=[c.fact_id] + [w[0].fact for w in weak],
                                 text=f"On the {q} call management described cash generation positively, while in {ytd} " + " and ".join(w[2] for w in weak) + ".",
                                 implication="Ask what management means by strong cash generation: before capex, before working capital, or a single quarter."))
        elif theme == "Margins" and not lg.fin:
            mc = lg.n.margin_change(q, P.shift_year(q))
            if mc and mc.value <= -1.5 and (q, "margin") not in seen:
                seen.add((q, "margin"))
                out.append(Point(id=f"cv:{q.replace(' ', '')}:margin", rule="commentary_vs_numbers", severity=2, evidence=[c.fact_id, mc.fact],
                                 text=f"On the {q} call management described margins positively, while the reported EBITDA margin for {q} moved {lg.facts.items[mc.fact].display} year on year.",
                                 implication="Check whether management is quoting an adjusted or segment margin; the reported consolidated margin is what the statement shows."))
    return out
