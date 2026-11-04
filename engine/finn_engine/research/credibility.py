"""Management credibility: what management said, set against what was later reported.

There is no trust score. Weighting delivery against revisions against cash
would be an opinion dressed as a number. Each indicator instead reports what
was observed, with its count, and every observation links to the statement
and the reported figure behind it. A rate (for example "kept 4 of 6") is
stated only when there are at least MIN_CLOSED closed explicit targets across
at least MIN_YEARS fiscal years; below that the indicator says how much
history exists and lists it without a rate.

Four kinds of information stay separate throughout:

* explicit guidance    a number and a period, in management's words (ledger, explicit)
* qualitative remarks  a direction or worded quantity, or commentary (ledger, not explicit; outlook claims)
* reported outcomes    figures from the filed statements, and FINN's computations on them
* interpretation       sentences written by fixed rules from the above (optionally rephrased by a
                       model, accepted only if every number in it is in the cited facts)

Nothing here reads a document: it works on the ledger, the numbers and the
claims that the rest of the pipeline already built and audited.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Callable

from . import periods as P
from .financials import Numbers, Val
from .ledger import MARGIN_NUM, Ledger
from .metrics import BY_ID
from .models import Claim, Doc, LedgerEntry

MIN_CLOSED = 4  # closed explicit targets before a rate is stated
MIN_YEARS = 2  # ... spanning at least this many fiscal years
AT_MIDPOINT_PP = 0.15  # |actual - midpoint| within this (pp) counts as "at the midpoint"
AT_MIDPOINT_PCT = 0.025  # ... or within 2.5% of the midpoint for amounts

FAMILY = {
    "revenue": "Revenue", "revenue_growth_cc": "Revenue", "pat": "Profit", "ebitda": "Profit",
    "ebitda_margin": "Margins", "ebit_margin": "Margins", "gross_margin": "Margins", "pat_margin": "Margins",
    "capex": "Capex", "net_debt": "Balance sheet", "wc_days": "Balance sheet",
    "credit_cost": "Asset quality", "gnpa": "Asset quality", "nim": "Margins", "loan_growth": "Loan growth", "aum_growth": "Loan growth",
}
CLOSED = ("delivered", "ahead", "missed")
KEPT = ("delivered", "ahead")
ADVERSE = {"up": "lowered", "down": "raised"}


def _times(n: int) -> str:
    return {0: "never", 1: "once", 2: "twice"}.get(n, f"{n} times")


def _fy(period: str | None) -> int | None:
    p = P.parse(period or "")
    return p[1] if p else None


def _fylab(fy: int) -> str:
    return f"FY{fy % 100:02d}"


def _years(es: list[LedgerEntry]) -> list[str]:
    return sorted({_fylab(y) for e in es if (y := _fy(e.period))})


def _span(years: list[str]) -> str:
    return years[0] if len(years) == 1 else f"{years[0]}–{years[-1]}" if years else ""


def _pct_metric(e: LedgerEntry) -> bool:
    return BY_ID[e.metric].kind in ("growth", "level")


def _mid(band: dict | None) -> float | None:
    if not band or band.get("low") is None or band.get("high") is None or band["kind"] not in ("range", "point"):
        return None
    return (band["low"] + band["high"]) / 2


def _actual_in_band_units(e: LedgerEntry, facts: dict) -> float | None:
    f = facts.get(e.actual_fact or "")
    if not f or f.value is None:
        return None
    return f.value * 100 if f.unit in ("growth", "pct") else f.value


def _final_band(e: LedgerEntry) -> dict | None:
    return next((h.band for h in reversed(e.history) if h.band), None)


def _first_band(e: LedgerEntry) -> dict | None:
    return next((h.band for h in e.history if h.band), None)


def _meets(band: dict, actual: float, e: LedgerEntry) -> bool:
    """Same test as the ledger: inside the band, with the metric's tolerance unless the band is an 'around' reading."""
    m = BY_ID[e.metric]
    lo, hi = band.get("low"), band.get("high")
    if band["kind"] == "point" and lo != hi:
        tol = 0.0
    elif m.kind in ("growth", "level"):
        tol = m.tol
    else:
        tol = m.tol * abs(hi if hi is not None else lo or 0)
    ok_lo = lo is None or actual >= lo - tol
    ok_hi = hi is None or actual <= hi + tol
    if m.better == "up":
        return ok_lo
    return ok_hi


class Credibility:
    def __init__(self, lg: Ledger, n: Numbers, docs: dict[str, Doc], claims: list[Claim], is_financial: bool):
        self.lg, self.n, self.docs, self.claims, self.fin = lg, n, docs, claims, is_financial
        self.f = lg.facts.items
        self.guid = [e for e in lg.entries if e.kind == "guidance"]
        self.closed = [e for e in self.guid if e.explicit and e.verdict in CLOSED]

    # ------------------------------------------------------------ indicators
    def delivery(self) -> dict:
        es = sorted(self.closed, key=lambda e: (P.sort_key(e.period or ""), e.metric_label))
        years = _years(es)
        kept = [e for e in es if e.verdict in KEPT]
        enough = len(es) >= MIN_CLOSED and len(years) >= MIN_YEARS
        by_fam: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for e in es:
            by_fam[FAMILY.get(e.metric, BY_ID[e.metric].label)][0 if e.verdict in KEPT else 1] += 1
        if not es:
            headline = "No explicit target has reached the end of its period in the documents read."
        elif enough:
            headline = f"Kept {len(kept)} of {len(es)} explicit targets whose period has closed ({_span(years)})."
        else:
            headline = (f"{len(es)} explicit target{'s have' if len(es) != 1 else ' has'} closed ({_span(years) or 'none'}): {len(kept)} kept. "
                        f"FINN states a rate only from {MIN_CLOSED} closed targets across {MIN_YEARS} fiscal years.")
        return {
            "id": "delivery", "title": "Guidance delivery", "question": "When management gave a number, did the reported figure land within it?",
            "status": "observed" if enough else "insufficient" if es else "none", "n": len(es), "years": years,
            "headline": headline,
            "stat": {"kept": len(kept), "missed": len(es) - len(kept), "rate": round(len(kept) / len(es), 3) if enough else None},
            "by_family": [{"family": k, "kept": v[0], "missed": v[1]} for k, v in sorted(by_fam.items())],
            "rows": [self._row(e) for e in es],
            "method": f"Closed explicit targets only. Kept = delivered or ahead; the ledger's tolerance applies. A rate needs at least {MIN_CLOSED} targets across {MIN_YEARS} fiscal years.",
        }

    def _row(self, e: LedgerEntry, **extra) -> dict:
        first = next((h for h in e.history if h.band), None)
        return {"ledger": e.id, "metric": e.metric_label, "period": e.period, "target": e.target, "first_target": first.target if first else None,
                "stated_on": first.date if first else None, "verdict": e.verdict, "actual": e.actual_fact,
                "evidence": [x for x in e.evidence if x], **extra}

    def landing(self) -> dict:
        """Where closed targets landed relative to the midpoint of the stated range, on the side that matters."""
        rows = []
        for e in sorted(self.closed, key=lambda e: P.sort_key(e.period or "")):
            band = _final_band(e)
            mid, act = _mid(band), _actual_in_band_units(e, self.f)
            if mid is None or act is None or (band and band["low"] == band["high"]):
                continue
            pct = _pct_metric(e)
            off = act - mid if pct else (act - mid) / abs(mid) if mid else None
            if off is None:
                continue
            sign = 1 if BY_ID[e.metric].better == "up" else -1
            fav = off * sign
            near = abs(off) <= (AT_MIDPOINT_PP if pct else AT_MIDPOINT_PCT)
            side = "at" if near else "favourable" if fav > 0 else "adverse"
            off_s = f"{off:+.1f} pp" if pct else f"{off * 100:+.1f}%"
            rows.append(self._row(e, midpoint=round(mid, 4), offset=round(off, 4), offset_display=off_s, side=side))
        enough = len(rows) >= MIN_CLOSED and len(_years([self._entry(r["ledger"]) for r in rows])) >= MIN_YEARS
        counts = {k: sum(1 for r in rows if r["side"] == k) for k in ("favourable", "at", "adverse")}
        if not rows:
            headline = "No closed target was a range or an approximate figure, so there is no midpoint to compare with."
        elif enough:
            headline = (f"Against the midpoint of the stated range, closed targets landed on the favourable side {_times(counts['favourable'])}, "
                        f"near it {_times(counts['at'])} and on the adverse side {_times(counts['adverse'])}.")
        else:
            headline = f"{len(rows)} closed target{'s' if len(rows) != 1 else ''} with a range to compare; too few to call a tendency."
        return {
            "id": "landing", "title": "Where results landed in the range", "question": "Does management guide conservatively, or tend to land short of the middle?",
            "status": "observed" if enough else "insufficient" if rows else "none", "n": len(rows), "headline": headline, "stat": counts if enough else None, "rows": rows,
            "method": (f"Ranges and 'around' figures only. Offset = actual - midpoint, in percentage points for growth and margins, and as a share of the midpoint for amounts. "
                       f"'Favourable' depends on the metric: above the midpoint for growth, margins and capex; below it for credit cost and debt. Within "
                       f"{AT_MIDPOINT_PP} pp or {AT_MIDPOINT_PCT:.0%} counts as at the midpoint. Counts are shown only from {MIN_CLOSED} targets across {MIN_YEARS} years."),
        }

    def _entry(self, lid: str) -> LedgerEntry:
        return next(e for e in self.lg.entries if e.id == lid)

    def revisions(self) -> dict:
        threads = []
        for e in sorted(self.guid, key=lambda e: P.sort_key(e.period or "")):
            if not e.explicit:
                continue
            changes = [h for h in e.history if h.change in ("raised", "lowered", "changed")]
            if not changes:
                continue
            adverse = [h for h in changes if h.change == ADVERSE.get(e.better)]
            row = self._row(e, changes=[{"call": h.call, "date": h.date, "change": h.change, "target": h.target, "fact": h.fact_id} for h in changes],
                            adverse=len(adverse))
            if e.verdict in CLOSED:
                fb, act = _first_band(e), _actual_in_band_units(e, self.f)
                if fb and act is not None:
                    row["first_target_met"] = _meets(fb, act, e)
            threads.append(row)
        # Repeated pattern: the same metric revised against the company in two or more fiscal years.
        by_metric: dict[str, set[str]] = defaultdict(set)
        for t in threads:
            if t["adverse"]:
                by_metric[t["metric"]].add(t["period"] or "")
        repeated = {k: sorted(v, key=P.sort_key) for k, v in by_metric.items() if len({_fy(p) for p in v}) >= 2}
        met_only_revised = [t for t in threads if t.get("first_target_met") is False and t["verdict"] in KEPT]
        explicit_threads = sum(1 for e in self.guid if e.explicit)
        if not explicit_threads:
            headline = "Management gave no explicit targets in the documents read."
        elif not threads:
            headline = f"None of the {explicit_threads} explicit targets was changed after it was first stated."
        else:
            adv = sum(1 for t in threads if t["adverse"])
            headline = f"{len(threads)} of {explicit_threads} explicit targets were changed before their period closed; {adv} of those changes went against the company."
        return {
            "id": "revisions", "title": "Guidance revisions", "question": "How often were targets changed mid-period, and in which direction?",
            "status": "observed" if threads else "none", "n": len(threads), "headline": headline, "rows": threads,
            "repeated": [{"metric": k, "periods": v} for k, v in repeated.items()],
            "met_only_after_revision": [t["ledger"] for t in met_only_revised],
            "method": ("A revision is a later statement with a different number for the same metric and period. 'Against the company' means lowered for growth, margins and capex, "
                       "raised for credit cost and debt. Two documents disagreeing in the same quarter are reported as a contradiction, not counted as a revision."),
        }

    def capex(self) -> dict:
        rows = []
        for e in sorted([e for e in self.guid if e.metric == "capex" and e.explicit], key=lambda e: P.sort_key(e.period or "")):
            fb, lb = _first_band(e), _final_band(e)
            act = self.f.get(e.actual_fact or "")
            closed = e.verdict in CLOSED
            ratio = None
            if closed and act and fb and _mid(fb):
                ratio = self.n._computed(f"c:cred:capex:{(e.period or '').replace(' ', '')}", f"Capex {e.period} as a share of the first-stated plan", round(act.value / _mid(fb), 3), "pct", e.period,
                                         f"actual capex ÷ first-stated plan ({_mid(fb):,.0f} cr)", [act.id] + ([e.history[0].fact_id] if e.history and e.history[0].fact_id else []))
            rows.append(self._row(e, final_target=e.target, closed=closed, execution=ratio.fact if ratio else None,
                                  execution_value=ratio.value if ratio else None))
        done = [r for r in rows if r["execution"]]
        if not rows:
            headline = "Management gave no capex figure in the documents read."
        elif not done:
            headline = "Capex was guided, but no guided year has closed yet."
        else:
            # The text quotes the cited fact's own display, so the two can't disagree on rounding.
            parts = ", ".join(f"{r['period']} {self.f[r['execution']].display}" for r in done)
            headline = f"Capex against the first-stated plan: {parts}."
        return {
            "id": "capex", "title": "Capex execution", "question": "Did the company spend what it said it would?",
            "status": "observed" if len(done) >= 2 else "insufficient" if done or rows else "none", "n": len(done), "headline": headline, "rows": rows,
            "method": "Capex = purchase of property, plant and equipment in the cash flow statement (year-end filing). The plan is the first figure stated for the year, so mid-year cuts don't hide under-spending.",
        }

    def metric_track(self, fam: str, title: str, question: str) -> dict:
        """Revenue or margins: every statement for a year (explicit, qualitative, or not checkable) next to the reported figure."""
        es = sorted([e for e in self.guid if FAMILY.get(e.metric) == fam], key=lambda e: (P.sort_key(e.period or ""), e.metric_label))
        rows = []
        for e in es:
            kind = "explicit" if e.explicit else "qualitative"
            rows.append(self._row(e, kind=kind, note=e.status_note if e.verdict != "unverifiable" else e.detail))
        closed = [e for e in es if e.explicit and e.verdict in CLOSED]
        path = self._annual_path(fam)
        word = {"Revenue": "revenue", "Margins": "margin"}.get(fam, fam.lower())
        uncheckable = [e for e in es if e.verdict == "unverifiable" and e.explicit]
        if closed:
            headline = f"{sum(1 for e in closed if e.verdict in KEPT)} of {len(closed)} closed explicit {word} targets kept."
        elif uncheckable and len(uncheckable) == sum(1 for e in es if e.explicit):
            basis = {"revenue_growth_cc": "constant currency"}.get(uncheckable[0].metric, BY_ID[uncheckable[0].metric].label.lower())
            headline = f"Every explicit {word} target was stated on a basis the filed statements don't report ({basis}), so none can be scored; reported growth is shown alongside."
        else:
            headline = f"No explicit {word} target has closed yet." if es else f"Management gave no {word} guidance in the documents read."
        return {"id": fam.lower().replace(" ", "_"), "title": title, "question": question, "status": "observed" if closed else "insufficient" if es else "none",
                "n": len(closed), "headline": headline, "rows": rows, "path": path,
                "method": "Each statement is shown with the reported figure for its period. Constant-currency and worded statements are listed but not scored."}

    def _annual_path(self, fam: str) -> list[dict]:
        out = []
        fys = sorted({p for p in self.n.agg if p.startswith("FY")}, key=P.sort_key)
        for fy in fys:
            if fam == "Revenue":
                v = self.n.growth(fy, "revenue")
            elif fam == "Margins" and not self.fin:
                v = self.n.margin(fy, "ebit" if any(e.metric == "ebit_margin" for e in self.guid) else "ebitda")
            else:
                v = None
            if v:
                out.append({"period": fy, "fact": v.fact})
        return out

    def cash(self) -> dict:
        if self.fin:
            return {"id": "cash", "title": "Cash generation against profit", "question": "Does reported profit turn into cash?", "status": "none", "n": 0,
                    "headline": "Not meaningful for a lender: operating cash flow includes the growth of the loan book.", "rows": [], "method": "",
                    "management_said": [], "contradictions": []}
        rows = []
        for per in [p for p in self.n.cf_periods() if p.startswith("FY")]:
            ocf, pat, eb = self.n.cf_val(per, "cfo"), self.n.flow(per, "pat"), self.n.ebitda(per)
            r1 = self.n.ratio(f"c:{per}:cfo_pat", f"OCF ÷ PAT, {per}", ocf, pat, "operating cash flow ÷ profit after tax", per)
            r2 = self.n.ratio(f"c:{per}:cfo_ebitda", f"Cash conversion (OCF ÷ EBITDA), {per}", ocf, eb, "operating cash flow ÷ EBITDA", per)
            fcf = self.n.fcf(per)
            rows.append({"period": per, "ocf_pat": r1.fact if r1 else None, "ocf_ebitda": r2.fact if r2 else None, "fcf": fcf.fact if fcf else None,
                         "ocf_pat_value": r1.value if r1 else None, "ocf_ebitda_value": r2.value if r2 else None})
        said = [c.fact_id for c in self.claims if c.theme == "Cash generation" and c.fact_id]
        flagged = [p for p in self.lg_points() if p.id.endswith(":cash")]
        vals = [r["ocf_ebitda_value"] for r in rows if r["ocf_ebitda_value"] is not None]
        if len(vals) >= 2:
            headline = f"Operating cash flow was {min(vals):.0%}–{max(vals):.0%} of EBITDA across {rows[0]['period']}–{rows[-1]['period']}."
        elif vals:
            headline = f"One full year of cash flow read: OCF was {vals[0]:.0%} of EBITDA."
        else:
            headline = "No full-year cash flow statement was read."
        return {"id": "cash", "title": "Cash generation against profit", "question": "Does reported profit turn into cash, and does management describe it fairly?",
                "status": "observed" if len(vals) >= 2 else "insufficient" if vals else "none", "n": len(vals), "headline": headline, "rows": rows,
                "management_said": said, "contradictions": [p.id for p in flagged],
                "method": "Full years from the year-end cash flow statement. What management said about cash is set against the ratio for the same period."}

    def silence(self) -> dict:
        rows = []
        for e in sorted(self.guid, key=lambda e: P.sort_key(e.period or "")):
            if not e.explicit or e.verdict == "unverifiable":
                continue
            quiet = [h for h in e.history if h.change in ("not repeated", "withdrawn", "softened")]
            if not quiet:
                continue
            outcome = "missed" if e.verdict == "missed" else "withdrawn" if (e.status_note or "").startswith("withdrawn") else e.verdict
            behind = "behind" in (e.status_note or "")
            if e.verdict in KEPT:
                continue  # went quiet and then delivered: not informative
            rows.append(self._row(e, quiet=[{"call": h.call, "date": h.date, "change": h.change} for h in quiet], outcome=outcome, behind=behind))
        missed_n = sum(1 for r in rows if r["outcome"] == "missed")
        headline = (f"{len(rows)} explicit target{'s' if len(rows) != 1 else ''} went quiet (not repeated, withdrawn or restated in words) without being met"
                    + (f"; {missed_n} {'was' if missed_n == 1 else 'were'} then missed." if missed_n else ".")) if rows else \
                   "No explicit target went quiet without being met."
        return {"id": "silence", "title": "Targets that went quiet", "question": "Does management stop mentioning targets it is going to miss?",
                "status": "observed" if rows else "none", "n": len(rows), "headline": headline, "rows": rows,
                "method": "A target goes quiet when a later complete call transcript doesn't mention it before its period ends, when it is withdrawn, or when the number is restated only in words."}

    def quoted_figures(self) -> dict:
        es = [e for e in self.lg.entries if e.kind == "assertion" and e.verdict != "unverifiable"]
        counts = {k: sum(1 for e in es if e.verdict == k) for k in ("consistent", "partial", "contradicted")}
        headline = (f"{counts['consistent']} of {len(es)} figures management quoted about reported periods match the statements"
                    + (f"; {counts['contradicted']} contradicted." if counts["contradicted"] else ".")) if es else "No checkable figures quoted about reported periods."
        return {"id": "quoted", "title": "Figures quoted on calls", "question": "When management describes a reported quarter, do the statements agree?",
                "status": "observed" if es else "none", "n": len(es), "headline": headline, "stat": counts,
                "rows": [{"ledger": e.id, "metric": e.metric_label, "period": e.period, "verdict": e.verdict, "evidence": e.evidence} for e in es],
                "method": "Checked on every plausible basis (year on year, sequential, level) before a figure is called contradicted."}

    def lg_points(self):
        from .ledger import discrepancies
        if not hasattr(self, "_pts"):
            self._pts = discrepancies(self.lg)
        return self._pts

    # ------------------------------------------------------------ timeline
    def lanes(self) -> list[dict]:
        groups: dict[tuple, list[LedgerEntry]] = defaultdict(list)
        for e in self.guid:
            groups[(e.metric, e.segment)].append(e)
        out = []
        for (metric, segment), es in groups.items():
            m = BY_ID[metric]
            pct = m.kind in ("growth", "level")
            statements = []
            for e in sorted(es, key=lambda e: P.sort_key(e.period or "")):
                end = P.end_of(e.period or "")
                for i, h in enumerate(e.history):
                    if not h.date or (h.change == "not repeated" and not e.explicit):
                        continue  # silence about a worded target says nothing
                    nxt = next((x.date for x in e.history[i + 1:] if x.date and x.change not in ("also stated",)), None)
                    statements.append({
                        "ledger": e.id, "period": e.period, "period_end": end.isoformat() if end else None, "date": h.date, "until": min(filter(None, [nxt, end.isoformat() if end else None])) if (nxt or end) else None,
                        "change": h.change, "target": h.target, "band": h.band, "fact": h.fact_id, "call": h.call,
                        "kind": "explicit" if h.band else "silence" if h.change in ("not repeated", "withdrawn") else "qualitative",
                    })
            actuals = self._lane_actuals(metric, segment)
            outcomes = []
            for e in es:
                end = P.end_of(e.period or "")
                a = self.f.get(e.actual_fact or "")
                if not a:
                    continue
                ytd_end = P.end_of(a.period) if a.period and a.period != e.period else None
                outcomes.append({"ledger": e.id, "period": e.period, "date": (ytd_end or end).isoformat() if (ytd_end or end) else None, "verdict": e.verdict, "status_note": e.status_note,
                                 "fact": a.id, "value": (a.value * 100 if a.unit in ("growth", "pct") else a.value), "closed": e.verdict in CLOSED,
                                 "ytd": a.period if a.period != e.period else None})
            label = m.label + (f" ({segment})" if segment else "")
            out.append({"id": f"lane:{metric}:{segment or ''}", "metric": metric, "label": label, "unit": "pct" if pct else "cr", "better": m.better,
                        "kind": "growth" if m.kind == "growth" else m.kind, "checkable": m.unverifiable is None, "reason": m.unverifiable,
                        "statements": sorted(statements, key=lambda s: s["date"]), "actuals": actuals, "outcomes": outcomes})
        rank = ["Revenue", "Margins", "Profit", "Capex", "Balance sheet", "Asset quality", "Loan growth"]
        return sorted(out, key=lambda l: (not l["checkable"], rank.index(FAMILY[l["metric"]]) if FAMILY.get(l["metric"]) in rank else 99, l["label"]))

    def _lane_actuals(self, metric: str, segment: str | None) -> list[dict]:
        """The reported path for a lane: quarterly where it exists, otherwise at each period end."""
        out = []
        def add(per: str, v: Val | None, kind: str) -> None:
            end = P.end_of(per)
            if v and end:
                f = self.f[v.fact]
                out.append({"period": per, "date": end.isoformat(), "fact": v.fact, "value": f.value * 100 if f.unit in ("growth", "pct") else f.value, "kind": kind})
        qs = self.n.quarters()
        if metric in MARGIN_NUM:
            for q in qs:
                add(q, self.n.margin(q, MARGIN_NUM[metric]), "quarter")
        elif metric in ("revenue", "revenue_growth_cc") and not segment:
            for q in qs:
                add(q, self.n.growth(q, "revenue"), "quarter yoy" if metric == "revenue" else "context")
        elif metric in ("pat", "ebitda"):
            for q in qs:
                add(q, self.n.growth(q, metric), "quarter yoy")
        elif metric == "capex":
            for per in self.n.cf_periods():
                add(per, self.n.capex(per), "ytd" if per.startswith("H") else "year")
        elif metric == "net_debt":
            for d in self.n.bs_dates():
                add(d, self.n.net_debt(d), "balance sheet")
        elif metric == "credit_cost":
            for per in self.n.cf_periods() + [d for d in self.n.bs_dates() if d not in self.n.cf_periods()]:
                add(per, self.n.credit_cost(per), "ytd" if per.startswith("H") else "year")
        elif metric == "loan_growth":
            for d in self.n.bs_dates():
                add(d, self.n.loan_growth_ytd(d), "since March")
        elif segment:
            for q in qs:
                g = self.lg.segment_growth(q, segment)
                add(q, g, "quarter yoy")
        seen: set[str] = set()
        return [x for x in sorted(out, key=lambda x: x["date"]) if not (x["fact"] in seen or seen.add(x["fact"]))]  # type: ignore[func-returns-value]

    # ------------------------------------------------------------ interpretation
    def interpret(self, ind: dict[str, dict]) -> list[dict]:
        """Fixed rules over the indicators. Each sentence cites the facts its numbers come from."""
        out: list[dict] = []
        d = ind["delivery"]
        def ev(rows: list[dict]) -> list[str]:
            return [x for r in rows for x in r["evidence"][:3]]
        if d["status"] == "observed":
            misses = [r for r in d["rows"] if r["verdict"] == "missed"]
            fams = {FAMILY.get(self._entry(r["ledger"]).metric) for r in misses}
            text = f"Management kept {d['stat']['kept']} of {d['n']} explicit targets whose period has closed ({_span(d['years'])})."
            if misses and len(fams) == 1:
                text += f" {'Both' if len(misses) == 2 else 'All'} {len(misses)} misses were {next(iter(fams)).lower()} targets." if len(misses) > 1 else f" The miss was a {next(iter(fams)).lower()} target."
            out.append({"id": "i:delivery", "rule": "delivery_observed", "text": text, "evidence": ev(d["rows"])})
        elif d["status"] == "insufficient":
            out.append({"id": "i:history", "rule": "insufficient_history", "evidence": ev(d["rows"]),
                        "text": f"There isn't enough closed history to judge delivery: {d['n']} explicit target{'s' if d['n'] != 1 else ''} closed in the documents read, against the {MIN_CLOSED} across {MIN_YEARS} years FINN requires."})
        lnd = ind["landing"]
        if lnd["status"] == "observed" and lnd["stat"]:
            c = lnd["stat"]
            if c["adverse"] >= max(2, (2 * lnd["n"] + 2) // 3):
                out.append({"id": "i:landing", "rule": "lands_short", "evidence": ev(lnd["rows"]),
                            "text": f"Closed targets have tended to land on the unfavourable side of the stated range ({c['adverse']} of {lnd['n']}): read new ranges from their less favourable end."})
            elif c["favourable"] >= max(2, (2 * lnd["n"] + 2) // 3):
                out.append({"id": "i:landing", "rule": "lands_long", "evidence": ev(lnd["rows"]),
                            "text": f"Closed targets have tended to land on the favourable side of the stated range ({c['favourable']} of {lnd['n']}), consistent with conservative guidance."})
        # The same metric missed in two or more closed years: a pattern regardless of the total count.
        missed_by: dict[str, list[LedgerEntry]] = defaultdict(list)
        for e in self.closed:
            if e.verdict == "missed":
                missed_by[e.metric_label].append(e)
        for label, es in missed_by.items():
            if len({_fy(e.period) for e in es}) >= 2:
                es = sorted(es, key=lambda e: P.sort_key(e.period or ""))
                sides = {"above" if (_actual_in_band_units(e, self.f) or 0) > ((_final_band(e) or {}).get("high") or 1e18) else "below" for e in es}
                parts = "; ".join(f"{e.period}: {self.f[e.actual_fact].display.lstrip('+')} against {e.target}" for e in es if e.actual_fact)
                out.append({"id": f"i:miss:{es[0].metric}", "rule": "repeated_miss_same_metric", "evidence": [x for e in es for x in e.evidence[:3]],
                            "text": f"{label} missed the guided range in {len(es)} closed years{', each time ' + next(iter(sides)) + ' it' if len(sides) == 1 else ''} ({parts})."})
        rv = ind["revisions"]
        for rep in rv["repeated"]:
            rows = [r for r in rv["rows"] if r["metric"] == rep["metric"] and r["adverse"]]
            out.append({"id": f"i:rev:{rep['metric']}", "rule": "repeated_adverse_revision", "evidence": [ch["fact"] for r in rows for ch in r["changes"] if ch["fact"]],
                        "text": f"{rep['metric']} guidance was cut during the year for {', '.join(rep['periods'])}."})
        for lid in rv["met_only_after_revision"]:
            r = next(x for x in rv["rows"] if x["ledger"] == lid)
            out.append({"id": f"i:revmet:{lid}", "rule": "met_only_after_revision", "evidence": r["evidence"],
                        "text": f"{r['metric']} for {r['period']} was met only against the revised target ({r['target']}); the first figure stated was {r['first_target']}."})
        cx = ind["capex"]
        done = [r for r in cx["rows"] if r["execution_value"] is not None]
        if len(done) >= 2 and all(r["execution_value"] < 0.95 for r in done):
            out.append({"id": "i:capex", "rule": "capex_below_plan", "evidence": [r["execution"] for r in done],
                        "text": f"Capex has come in below the first-stated plan in each closed year ({', '.join(f'{r['period']}: {self.f[r['execution']].display}' for r in done)}); expect the current plan to slip unless the reason has changed."})
        sl = ind["silence"]
        for r in [x for x in sl["rows"] if x["outcome"] == "missed"]:
            n_q = sum(1 for q in r["quiet"] if q["change"] == "not repeated")
            out.append({"id": f"i:quiet:{r['ledger']}", "rule": "quiet_then_missed", "evidence": r["evidence"],
                        "text": f"The {r['metric'].lower()} target for {r['period']} ({r['target']}) wasn't repeated on {n_q} call{'s' if n_q != 1 else ''} before the year closed, and was missed."})
        current = [e for e in self.guid if e.explicit and e.verdict in ("pending", "dropped")]
        behind = [e for e in current if "behind" in (e.status_note or "") or e.status_note == "at risk"]
        if behind and d["status"] == "observed" and d["stat"]["rate"] is not None and d["stat"]["rate"] >= 0.75:
            out.append({"id": "i:break", "rule": "record_vs_current", "evidence": [x for e in behind for x in e.evidence[:2]],
                        "text": f"The record on closed targets is good, but {len(behind)} of {len(current)} current targets are behind on the latest reported figures; the record alone isn't a reason to trust this year's numbers."})
        elif behind:
            text = ("The one explicit target still open is behind on the latest reported figures." if len(current) == 1 else
                    f"{len(behind)} of {len(current)} explicit targets still open are behind on the latest reported figures.")
            out.append({"id": "i:current", "rule": "current_behind", "evidence": [x for e in behind for x in e.evidence[:2]], "text": text})
        cash = ind["cash"]
        if cash.get("contradictions"):
            p = next(x for x in self.lg_points() if x.id in cash["contradictions"])
            out.append({"id": "i:cash", "rule": "cash_claim_vs_statement", "evidence": p.evidence, "text": p.text})
        return out


def build(lg: Ledger, n: Numbers, docs: dict[str, Doc], claims: list[Claim], is_financial: bool,
          rephrase: Callable[[str, str], str | None] | None = None) -> dict:
    c = Credibility(lg, n, docs, claims, is_financial)
    ind = {
        "delivery": c.delivery(),
        "landing": c.landing(),
        "revisions": c.revisions(),
        "capex": c.capex(),
        "revenue": c.metric_track("Revenue", "Revenue growth against what was guided", "How did revenue growth compare with what management said to expect?"),
        "margins": c.metric_track("Margins", "Margin progression", "Did margins move the way management said they would?"),
        "cash": c.cash(),
        "silence": c.silence(),
        "quoted": c.quoted_figures(),
    }
    interp = c.interpret(ind)
    for p in interp:
        p["method"] = "rules"
        if rephrase:
            allowed = " ".join([p["text"]] + [(c.f[x].display or "") + " " + (c.f[x].label or "") for x in p["evidence"] if x in c.f])
            alt = rephrase(p["text"], allowed)
            if alt:
                p["rules_text"], p["text"], p["method"] = p["text"], alt, "model, numbers checked"
    calls = sorted([d for d in docs.values() if d.kind == "transcript" and d.status == "parsed"], key=lambda d: d.filed_at.isoformat() if d.filed_at else "")
    contradiction_rules = ("assertion_contradicted", "commentary_vs_numbers", "documents_disagree")
    return {
        "window": {"calls": len(calls), "first_call": calls[0].period if calls else None, "last_call": calls[-1].period if calls else None,
                   "results": sum(1 for d in docs.values() if d.kind == "results" and d.status == "parsed"),
                   "closed_years": ind["delivery"]["years"]},
        "rules": {"min_closed": MIN_CLOSED, "min_years": MIN_YEARS,
                  "no_score": "FINN doesn't combine these indicators into a trust score: any weighting would be a judgement, not a measurement."},
        "indicators": list(ind.values()),
        "lanes": c.lanes(),
        "interpretation": interp,
        "contradictions": [p.model_dump() for p in c.lg_points() if p.rule in contradiction_rules],
    }


def model_rephraser(complete: Callable[[str], str], model: str) -> Callable[[str, str], str | None]:
    """Optional: a model may reword an interpretation. It is kept only if it adds nothing to the cited facts
    and FINN's own sentence: no new numbers, causes, judgements or names (see explain.grounded)."""
    import json
    import re

    from ..explain import grounded

    def rephrase(text: str, allowed: str) -> str | None:
        prompt = ("Reword this sentence for an investor in plain English. Keep every number exactly as given. Add no facts, causes, names or numbers.\n"
                  'Reply as JSON: {"text": "<one or two sentences>"}\n'
                  f"SENTENCE: {text}")
        try:
            raw = complete(prompt)
            m = re.search(r"\{.*\}", raw, re.S)
            alt = str(json.loads(m.group(0) if m else raw)["text"]).strip()
        except Exception:  # noqa: BLE001
            return None
        if not alt or len(alt) > 1.6 * len(text) + 40:
            return None
        ok, _ = grounded(alt, allowed + " " + text)
        return alt if ok else None

    rephrase.model = model  # type: ignore[attr-defined]
    return rephrase
