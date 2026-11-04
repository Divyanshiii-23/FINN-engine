"""The eight research sections, built only from facts already in the registry.

Each section returns plain data: fact IDs to display plus the gaps that
explain anything missing. Bull vs Bear is rule-based: each point names its
rule and cites the facts whose numbers it uses; a side with no triggered rule
says so instead of being padded.
"""

from __future__ import annotations

from . import periods as P
from .financials import Facts, Numbers, Val
from .ledger import Ledger, discrepancies
from .models import Claim, Doc, Gap, Identity, Point


def _f(v: Val | None) -> str | None:
    return v.fact if v else None


def business(idn: Identity, n: Numbers, overview: tuple[str, int, str, Doc] | None, facts: Facts) -> dict:
    gaps: list[Gap] = []
    desc = None
    if overview:
        text, page, heading, doc = overview
        from .models import Fact
        desc = facts.add(Fact(id=f"q:overview:{doc.id}", info_class="reported", label="Business description (company's own words)", quote=text,
                              doc_id=doc.id, page=page, section=heading, speaker="Company document", role="company"))
    else:
        gaps.append(Gap(area="Business description", detail="No annual report or presentation with an overview section was found, so the business isn't described in the company's words."))
    latest = n.latest()
    seg_q = next((q for q in reversed(n.quarters()) if q in n.seg), None)
    segments = []
    if seg_q:
        for name, v, share in n.segment_mix(seg_q):
            g = None
            prior = n._reported(n.seg, P.shift_year(seg_q), name, "seg")
            if prior and prior.value > 0:
                g = n._computed(f"c:{seg_q.replace(' ', '')}:seg:{name}:yoy", f"{name} revenue growth, {seg_q} YoY", v.value / prior.value - 1, "growth", seg_q, f"{seg_q} ÷ {P.shift_year(seg_q)} - 1", [v.fact, prior.fact])
            segments.append({"name": name, "share": round(share, 4), "fact": v.fact, "growth_fact": _f(g)})
    elif latest:
        gaps.append(Gap(area="Segments", detail="The results filings read have no segment note (single-segment company, or the note wasn't found)."))
    return {"description": desc, "industry": idn.industry, "segments": segments, "segment_period": seg_q, "gaps": [g.model_dump() for g in gaps]}


def snapshot(n: Numbers, is_fin: bool, mcap: tuple[float, str] | None, facts: Facts) -> dict:
    q = n.latest()
    if not q:
        return {"period": None, "rows": [], "gaps": [Gap(area="Financial snapshot", detail="No results filing could be read.").model_dump()]}
    keys = [("revenue", "Revenue"), ("nii", "Net interest income"), ("pat", "Profit after tax")] if is_fin else [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pat", "Profit after tax")]
    rows = []
    for k, label in keys:
        v = n.metric_amount(q, k)
        rows.append({"key": k, "label": label, "value": _f(v), "qoq": _f(n.qoq(q, k)), "yoy": _f(n.growth(q, k))})
    margins = [] if is_fin else [{"label": "EBITDA margin", "value": _f(n.margin(q, "ebitda")), "yoy_change": _f(n.margin_change(q, P.shift_year(q)))}]
    margins.append({"label": "PAT margin", "value": _f(n.margin(q, "pat")), "yoy_change": None})
    ttm_rev, ttm_pat = n.ttm(q), n.ttm(q, "pat")
    bsd = n.bs_dates()
    bal = []
    if bsd:
        d = bsd[-1]
        if is_fin:
            bal = [{"label": f"Loans, {d}", "value": _f(n.bs_val(d, "loans"))}, {"label": f"Debt to equity, {d}", "value": _f(n.debt_equity(d))}]
        else:
            bal = [{"label": f"Net debt, {d}", "value": _f(n.net_debt(d))}, {"label": f"Debt to equity, {d}", "value": _f(n.debt_equity(d))}]
    market = []
    if mcap:
        from .models import Fact
        mid = facts.add(Fact(id="m:mcap", info_class="reported", label="Market capitalisation (BSE scrip list)", value=mcap[0], unit="cr", display=f"₹{mcap[0]:,.0f} cr", note=f"Exchange market data, {mcap[1]}; not a company document."))
        market.append({"label": "Market cap", "value": mid})
        if ttm_pat and ttm_pat.value > 0:
            pe = n._computed("c:pe", f"Price to earnings (market cap ÷ TTM PAT to {q})", round(mcap[0] / ttm_pat.value, 1), "multiple", q, "market cap ÷ trailing-twelve-month PAT", [mid, ttm_pat.fact])
            market.append({"label": "P/E (TTM)", "value": pe.fact})
    return {"period": q, "basis": n.basis, "rows": rows, "margins": margins, "ttm": [{"label": "Revenue (TTM)", "value": _f(ttm_rev)}, {"label": "PAT (TTM)", "value": _f(ttm_pat)}],
            "balance": bal, "market": market, "gaps": []}


def trajectory(n: Numbers, is_fin: bool) -> dict:
    qs = n.quarters()[-8:]
    def series(fn) -> list[str | None]:
        return [_f(fn(q)) for q in qs]
    s = {
        "revenue": series(lambda q: n.flow(q, "revenue")),
        "pat": series(lambda q: n.flow(q, "pat")),
        "revenue_yoy": series(lambda q: n.growth(q, "revenue")),
        "pat_yoy": series(lambda q: n.growth(q, "pat")),
    }
    if is_fin:
        s["nii"] = series(lambda q: n.nii(q))
        s["impairment"] = series(lambda q: n.flow(q, "impairment"))
    else:
        s["ebitda"] = series(lambda q: n.ebitda(q))
        s["ebitda_margin"] = series(lambda q: n.margin(q, "ebitda"))
    annual = []
    for fy in sorted({p for p in n.agg if p.startswith("FY")}, key=P.sort_key):
        annual.append({"period": fy, "revenue": _f(n.flow(fy, "revenue")), "pat": _f(n.flow(fy, "pat")),
                       "ebitda": None if is_fin else _f(n.ebitda(fy)), "ebitda_margin": None if is_fin else _f(n.margin(fy, "ebitda")),
                       "revenue_growth": _f(n.growth(fy, "revenue"))})
    gaps = []
    if len(qs) < 8:
        gaps.append(Gap(area="Trajectory", detail=f"{len(qs)} quarters available from the results filings read (eight need four filings)."))
    restated = [r for r in n.restated if r["field"] in ("revenue", "pat", "pbt")]
    return {"quarters": qs, "series": s, "annual": annual, "restated": restated, "gaps": [g.model_dump() for g in gaps]}


def balance_sheet(n: Numbers, is_fin: bool) -> dict:
    dates = n.bs_dates()[-3:]
    if not dates:
        return {"dates": [], "rows": [], "gaps": [Gap(area="Balance sheet", detail="No statement of assets and liabilities was found. It is filed with half-year (Q2) and annual (Q4) results.").model_dump()]}
    if is_fin:
        spec = [("Loans", lambda d: n.bs_val(d, "loans")), ("Borrowings (all)", lambda d: n.bs_val(d, "borrowings")), ("Total equity", lambda d: n.bs_val(d, "total_equity")),
                ("Cash and cash equivalents", lambda d: n.bs_val(d, "cash")), ("Borrowings ÷ equity", lambda d: n.debt_equity(d)), ("Loan growth since March", lambda d: n.loan_growth_ytd(d) if not d.startswith("FY") else None)]
    else:
        spec = [("Total equity", lambda d: n.bs_val(d, "total_equity")), ("Borrowings (all)", lambda d: n.bs_val(d, "borrowings")),
                ("Cash and bank balances", lambda d: n.bs_val(d, "cash")), ("Current investments", lambda d: n.bs_val(d, "current_investments")),
                ("Net debt (negative = net cash)", lambda d: n.net_debt(d)), ("Debt to equity", lambda d: n.debt_equity(d)),
                ("Trade receivables", lambda d: n.bs_val(d, "receivables")), ("Inventories", lambda d: n.bs_val(d, "inventories")),
                ("Trade payables", lambda d: n.bs_val(d, "payables")), ("Working-capital days", lambda d: n.wc_days(d)), ("Receivable days", lambda d: n.receivable_days(d))]
    rows = [{"label": lab, "values": [_f(fn(d)) for d in dates]} for lab, fn in spec]
    rows = [r for r in rows if any(r["values"])]
    checks = [c for c in n.checks if c["check"].startswith("Total assets")]
    return {"dates": dates, "basis": n.basis, "rows": rows, "checks": checks, "gaps": []}


def cash_quality(n: Numbers, is_fin: bool) -> dict:
    periods = n.cf_periods()[-4:]
    if not periods:
        return {"periods": [], "rows": [], "flags": [], "gaps": [Gap(area="Cash quality", detail="No cash flow statement was found. It is filed with half-year (Q2) and annual (Q4) results.").model_dump()]}
    rows: list[dict] = []
    flags: list[dict] = []
    cfo = {p: n.cf_val(p, "cfo") for p in periods}
    rows.append({"label": "Operating cash flow", "values": [_f(cfo[p]) for p in periods]})
    if not is_fin:
        capex = {p: n.capex(p) for p in periods}
        fcf = {p: n.fcf(p) for p in periods}
        eb = {p: n.ebitda(p) for p in periods}
        pat = {p: n.flow(p, "pat") for p in periods}
        conv = {p: n.ratio(f"c:{p.replace(' ', '')}:cfo_ebitda", f"Cash conversion (OCF ÷ EBITDA), {p}", cfo[p], eb[p], "operating cash flow ÷ EBITDA", p) for p in periods}
        cpat = {p: n.ratio(f"c:{p.replace(' ', '')}:cfo_pat", f"OCF ÷ PAT, {p}", cfo[p], pat[p], "operating cash flow ÷ profit after tax", p) for p in periods}
        rows += [
            {"label": "Capex", "values": [_f(capex[p]) for p in periods]},
            {"label": "Free cash flow", "values": [_f(fcf[p]) for p in periods]},
            {"label": "EBITDA", "values": [_f(eb[p]) for p in periods]},
            {"label": "OCF ÷ EBITDA", "values": [_f(conv[p]) for p in periods]},
            {"label": "OCF ÷ PAT", "values": [_f(cpat[p]) for p in periods]},
        ]
        last = periods[-1]
        if conv[last]:
            v = conv[last].value
            if v < 0.6:
                flags.append({"tone": "bear", "rule": "ocf_ebitda<60%", "text": f"Operating cash flow covered {v:.0%} of EBITDA in {last}, below the 60% FINN treats as weak conversion.", "evidence": [conv[last].fact]})
            elif v >= 0.8:
                flags.append({"tone": "bull", "rule": "ocf_ebitda≥80%", "text": f"Operating cash flow covered {v:.0%} of EBITDA in {last}.", "evidence": [conv[last].fact]})
        if fcf[last] and fcf[last].value < 0:
            flags.append({"tone": "bear", "rule": "fcf<0", "text": f"Free cash flow was negative in {last}.", "evidence": [fcf[last].fact]})
    dates = n.bs_dates()
    if not is_fin and len(dates) >= 2:
        a, b = n.wc_days(dates[-2]), n.wc_days(dates[-1])
        if a and b and b.value - a.value >= 10:
            flags.append({"tone": "bear", "rule": "wc_days_up≥10", "text": f"Working-capital days rose from {a.value:.0f} to {b.value:.0f} between {dates[-2]} and {dates[-1]}.", "evidence": [a.fact, b.fact]})
    note = ("For a lender, operating cash flow includes the growth of the loan book, so it is negative while loans grow; "
            "FINN doesn't compute free cash flow or conversion ratios for lenders.") if is_fin else None
    return {"periods": periods, "rows": [r for r in rows if any(r["values"])], "flags": flags, "note": note, "gaps": []}


def guidance_section(lg: Ledger, claims: list[Claim], docs: dict[str, Doc]) -> dict:
    current = [e.id for e in lg.entries if e.kind == "guidance"]
    commentary: dict[str, list[str]] = {}
    for c in claims:
        if c.kind == "outlook" and c.fact_id:
            commentary.setdefault(c.theme or c.metric_label or "Other", []).append(c.fact_id)
    return {"entries": current, "commentary": [{"theme": k, "facts": v[:6]} for k, v in sorted(commentary.items(), key=lambda kv: -len(kv[1]))]}


def bull_bear(n: Numbers, lg: Ledger, is_fin: bool, cash_flags: list[dict] | None = None) -> dict:
    f = lg.facts.items
    bull: list[Point] = []
    bear: list[Point] = []
    q = n.latest()
    if q:
        g = n.growth(q, "revenue")
        prev = n.growth(P.prev_q(q), "revenue")
        if g and g.value >= 0.10:
            bull.append(Point(id="b:rev", rule="revenue_growth≥10%", text=f"Revenue grew {f[g.fact].display.lstrip('+')} year on year in {q}.", evidence=[g.fact]))
        if g and g.value < 0:
            bear.append(Point(id="x:rev", rule="revenue_decline", text=f"Revenue fell {f[g.fact].display.lstrip('-')} year on year in {q}.", evidence=[g.fact]))
        elif g and prev and prev.value - g.value >= 0.03:
            bear.append(Point(id="x:decel", rule="growth_deceleration≥3pp", text=f"Revenue growth slowed from {f[prev.fact].display} in {P.prev_q(q)} to {f[g.fact].display} in {q}.", evidence=[prev.fact, g.fact]))
        if not is_fin:
            mc = n.margin_change(q, P.shift_year(q))
            mq = n.margin(q, "ebitda")
            if mc and mq and mc.value >= 1:
                bull.append(Point(id="b:margin", rule="margin_expansion≥1pp", text=f"EBITDA margin was {f[mq.fact].display} in {q}, {f[mc.fact].display} on the year.", evidence=[mq.fact, mc.fact]))
            if mc and mq and mc.value <= -1:
                bear.append(Point(id="x:margin", rule="margin_contraction≥1pp", text=f"EBITDA margin was {f[mq.fact].display} in {q}, {f[mc.fact].display} on the year.", evidence=[mq.fact, mc.fact]))
        pg = n.growth(q, "pat")
        if pg and pg.value >= 0.15:
            bull.append(Point(id="b:pat", rule="pat_growth≥15%", text=f"Profit after tax grew {f[pg.fact].display.lstrip('+')} year on year in {q}.", evidence=[pg.fact]))
        if pg and pg.value <= -0.10:
            bear.append(Point(id="x:pat", rule="pat_decline≥10%", text=f"Profit after tax fell {f[pg.fact].display.lstrip('-')} year on year in {q}.", evidence=[pg.fact]))
    dates = n.bs_dates()
    if dates and not is_fin:
        nd, de = n.net_debt(dates[-1]), n.debt_equity(dates[-1])
        if nd and nd.value < 0:
            bull.append(Point(id="b:cash", rule="net_cash", text=f"Net cash of {f[nd.fact].display.lstrip('-')} at {dates[-1]} (cash, bank balances and current investments above borrowings).", evidence=[nd.fact]))
        if de and de.value > 1:
            bear.append(Point(id="x:lev", rule="debt_equity>1", text=f"Debt to equity of {f[de.fact].display} at {dates[-1]}.", evidence=[de.fact]))
    if is_fin and q:
        cc_now = n.credit_cost(f"H1 FY{q[-2:]}") if q.startswith("Q2") else None
        cc_then = n.credit_cost(f"FY{(int(q[-2:]) - 1):02d}") if cc_now else None
        if cc_now and cc_then and cc_now.value - cc_then.value >= 0.003:
            bear.append(Point(id="x:cc", rule="credit_cost_rising", text=f"Annualised credit cost rose to {f[cc_now.fact].display} in H1 FY{q[-2:]} from {f[cc_then.fact].display} for FY{int(q[-2:]) - 1:02d}.", evidence=[cc_now.fact, cc_then.fact]))
    if dates and not is_fin and len(dates) >= 2:
        a, b = n.net_debt(dates[0]), n.net_debt(dates[-1])
        if a and b and a.value > 0 and b.value < a.value * 0.9:
            bull.append(Point(id="b:delev", rule="net_debt_down≥10%", text=f"Net debt fell from {f[a.fact].display} at {dates[0]} to {f[b.fact].display} at {dates[-1]}.", evidence=[a.fact, b.fact]))
        if a and b and b.value > 0 and b.value > max(a.value, 0) * 1.2 + 1:
            bear.append(Point(id="x:lev_up", rule="net_debt_up≥20%", text=f"Net debt rose from {f[a.fact].display} at {dates[0]} to {f[b.fact].display} at {dates[-1]}.", evidence=[a.fact, b.fact]))
    for i, fl in enumerate(cash_flags or []):
        (bull if fl["tone"] == "bull" else bear).append(Point(id=f"{'b' if fl['tone'] == 'bull' else 'x'}:cash{i}", rule=fl.get("rule", "cash_quality"), text=fl["text"], evidence=fl["evidence"]))
    closed = [e for e in lg.entries if e.kind == "guidance" and e.verdict in ("delivered", "ahead", "missed")]
    kept = [e for e in closed if e.verdict in ("delivered", "ahead")]
    if kept:
        bull.append(Point(id="b:kept", rule="guidance_kept", text=f"Management met {len(kept)} of {len(closed)} explicit targets whose period has closed.", evidence=[x for e in kept for x in e.evidence[:2]]))
    for p in discrepancies(lg):
        if p.rule in ("guidance_missed", "guidance_dropped", "guidance_at_risk", "assertion_contradicted", "guidance_lowered") and p.severity >= 2:
            bear.append(Point(id="x:" + p.id, rule=p.rule, text=p.text, evidence=p.evidence, severity=p.severity))
    def dedupe(ps: list[Point]) -> list[Point]:
        seen: set[str] = set()
        out = []
        for p in ps:
            if p.id not in seen:
                seen.add(p.id)
                out.append(p)
        return out
    bull, bear = dedupe(bull), dedupe(bear)[:7]
    return {
        "bull": [p.model_dump() for p in bull],
        "bear": [p.model_dump() for p in bear],
        "note": "Rule-based: each point is a fixed test over the cited facts, and every number in it comes from those facts. A side with nothing listed means no rule fired on the evidence available, not that there is nothing to say.",
    }
