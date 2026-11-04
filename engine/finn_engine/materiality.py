"""Materiality scoring: deterministic, additive and inspectable.

score = type prior + size relative to the company + results surprise
        + seniority / pledge level + market reaction, clamped to 0-100.
Routine paperwork is capped at 30. Hard floors lift specific subtypes to 70.
Tiers: interrupt >= 65, brief >= 35, otherwise routine.

Every component carries its points, a plain-language detail and its inputs,
so the feed can show exactly why an item ranks where it does.
"""

from __future__ import annotations

from . import SCORING_VERSION
from .fmt import amount, cr, pct, pp
from .models import Classification, Company, Facts, Materiality, MaterialityComponent, MarketSignal, ResultsExtraction
from .taxonomy import CATEGORIES, FLOORS, prior

INTERRUPT, BRIEF = 65, 35
ROUTINE_CAP = 30
FLOOR_SCORE = 70
SIZE_CATEGORIES = {"mna", "fund_raise", "capex", "press_release", "litigation"}
SENIOR = {"Chief Executive Officer", "Chief Financial Officer", "Managing Director", "Chairman", "Chairperson", "Chief Operating Officer", "Whole-Time Director", "Whole Time Director", "Executive Director", "Statutory Auditor", "Statutory Auditors"}
JUNIOR = {"Independent Director", "Company Secretary", "Compliance Officer", "Non-Executive Director"}


def score(
    company: Company,
    cls: Classification,
    facts: Facts,
    results: ResultsExtraction | None,
    reaction: MarketSignal | None,
    reaction_pending: bool,
) -> Materiality:
    comps: list[MaterialityComponent] = []
    base = prior(cls.category, cls.subtype)
    comps.append(
        MaterialityComponent(
            code="type",
            label="Filing type",
            points=base,
            detail=f"{cls.category.replace('_', ' ')}{' / ' + cls.subtype.replace('_', ' ') if cls.subtype else ''} starts at {base}",
            inputs={"category": cls.category, "subtype": cls.subtype, "rule": cls.rule_id, "matched": cls.matched, "confidence": cls.confidence},
        )
    )
    if cls.method == "fallback":
        comps.append(MaterialityComponent(code="unclassified", label="Needs review", points=0, detail="No rule matched this filing; shown for review rather than hidden", inputs={}))

    # Size relative to the company
    if cls.category in SIZE_CATEGORIES and cls.subtype not in {"general", "clarification", "operating_update", "disruption"}:
        amt = max(facts.amounts_cr) if facts.amounts_cr else None
        use_revenue = cls.subtype == "order_win"
        ref = company.revenue_ttm_cr if use_revenue else company.market_cap_cr
        ref_name = "trailing revenue" if use_revenue else "market cap"
        if amt is None:
            comps.append(MaterialityComponent(code="size", label="Size", points=0, detail="No amount stated in the filing text", inputs={}))
        elif not ref:
            comps.append(MaterialityComponent(code="size", label="Size", points=0, detail=f"₹{amount(amt)} cr stated; size not assessed because no {ref_name} is on record", inputs={"amount_cr": amt}))
        else:
            ratio = amt / ref
            pts = 30 if ratio >= 0.25 else 25 if ratio >= 0.10 else 18 if ratio >= 0.05 else 10 if ratio >= 0.02 else 3 if ratio >= 0.005 else -8
            comps.append(
                MaterialityComponent(
                    code="size",
                    label="Size relative to the company",
                    points=pts,
                    detail=f"₹{amount(amt)} cr is {pct(ratio, signed=False)} of {ref_name} (₹{cr(ref, 0)} cr)",
                    inputs={"amount_cr": amt, ref_name.replace(" ", "_") + "_cr": ref, "ratio": round(ratio, 4)},
                )
            )

    # Results surprise
    if cls.category == "results" and cls.subtype in {"financial_results", "board_meeting_outcome"}:
        if results is None:
            comps.append(MaterialityComponent(code="results", label="Results figures", points=0, detail="Results document not analysed", inputs={}))
        elif results.status in {"failed", "unavailable"}:
            comps.append(MaterialityComponent(code="results", label="Results figures", points=0, detail=f"Figures not extracted: {results.reason}", inputs={"status": results.status}))
        else:
            pat = next((r for r in results.rows if r.key == "pat"), None)
            if pat and pat.current.value is not None and pat.current.value < 0:
                comps.append(MaterialityComponent(code="results_loss", label="Loss for the quarter", points=12, detail=f"PAT is a loss of ₹{cr(abs(pat.current.value))} cr", inputs={"pat_cr": pat.current.value}))
            elif pat and pat.yoy is not None:
                a = abs(pat.yoy)
                pts = 15 if a >= 0.30 else 8 if a >= 0.15 else 0
                comps.append(MaterialityComponent(code="results_pat", label="Profit change", points=pts, detail=f"PAT {pct(pat.yoy)} YoY", inputs={"pat_yoy": round(pat.yoy, 4)}))
            if results.margin and results.margin.get("current") is not None and results.margin.get("prev_y") is not None:
                d = (results.margin["current"] - results.margin["prev_y"]) * 100
                pts = 6 if abs(d) >= 1.5 else 0
                comps.append(MaterialityComponent(code="results_margin", label="Margin change", points=pts, detail=f"EBITDA margin {pct(results.margin['current'], signed=False)}, {pp(d)} YoY", inputs={"margin_change_pp": round(d, 2)}))
            if results.status == "needs_review":
                comps.append(MaterialityComponent(code="results_review", label="Extraction check", points=0, detail=f"Figures need review: {results.reason}", inputs={}))

    # Seniority
    if cls.category == "management_change" and facts.role:
        role = facts.role.title() if facts.role.islower() else facts.role
        # A senior executive leaving is a bigger signal than one arriving.
        leaving = cls.subtype in ("resignation", "resignation_with_concerns", "demise")
        pts = (25 if leaving else 15) if role in SENIOR else (0 if cls.subtype in ("resignation_with_concerns", "demise") else -10) if role in JUNIOR else 0
        if pts:
            comps.append(MaterialityComponent(code="seniority", label="Role", points=pts, detail=f"{role} {'is a senior executive role' if pts > 0 else 'is a board or compliance role, not an executive change'}", inputs={"role": role}))

    # Pledge level
    if cls.category == "pledging" and facts.pledge_pct is not None:
        pts = 18 if facts.pledge_pct >= 25 else 6 if facts.pledge_pct >= 10 else 0
        detail = f"{facts.pledge_pct}% of promoter holding pledged"
        if facts.pledge_prev_pct is not None:
            delta = facts.pledge_pct - facts.pledge_prev_pct
            detail += f", {pp(delta)} vs the previous disclosure"
            if delta >= 5:
                pts += 8
            elif delta >= 2:
                pts += 6
        comps.append(MaterialityComponent(code="pledge", label="Pledge level", points=pts, detail=detail, inputs={"pledge_pct": facts.pledge_pct, "previous_pct": facts.pledge_prev_pct}))

    # Market reaction
    if reaction_pending:
        comps.append(MaterialityComponent(code="reaction", label="Market reaction", points=0, detail="Market reaction not yet available: filed after the latest session in the price data", inputs={}))
    elif reaction is not None:
        pts = 0
        parts = []
        if reaction.split_or_bonus_on_date:
            parts.append("split or bonus on the day; price move not scored")
        else:
            if reaction.ret_z is not None:
                z = abs(reaction.ret_z)
                pts += 10 if z >= 3 else 6 if z >= 2 else 0
                parts.append(f"{pct(reaction.ret_1d)} on {reaction.date.isoformat()} ({reaction.ret_z:+.1f} standard deviations)")
            elif reaction.ret_1d is not None:
                parts.append(f"{pct(reaction.ret_1d)} on {reaction.date.isoformat()} (volatility baseline unavailable)")
            if reaction.vol_ratio_20d is not None:
                v = reaction.vol_ratio_20d
                pts += 8 if v >= 3 else 4 if v >= 2 else 0
                parts.append(f"volume {v:.1f}x its 20-day average")
        comps.append(MaterialityComponent(code="reaction", label="Market reaction", points=pts, detail=", ".join(parts) or "no move", inputs={"date": reaction.date.isoformat(), "ret_1d": reaction.ret_1d, "ret_z": reaction.ret_z, "vol_ratio_20d": reaction.vol_ratio_20d}))

    raw = sum(c.points for c in comps)
    value = max(0, min(100, round(raw)))
    if cls.routine and value > ROUTINE_CAP:
        comps.append(MaterialityComponent(code="routine_cap", label="Routine cap", points=ROUTINE_CAP - value, detail=f"Routine paperwork is capped at {ROUTINE_CAP}", inputs={}))
        value = ROUTINE_CAP
    floor = FLOORS.get((cls.category, cls.subtype or ""))
    if floor and value < FLOOR_SCORE:
        comps.append(MaterialityComponent(code="floor", label="Hard floor", points=FLOOR_SCORE - value, detail=floor, inputs={}))
        value = FLOOR_SCORE
    tier = "interrupt" if value >= INTERRUPT else "brief" if value >= BRIEF else "routine"
    return Materiality(score=value, tier=tier, raw_total=raw, components=comps, floor=floor, version=SCORING_VERSION)


CATEGORY_LABEL = {k: k.replace("_", " ").capitalize() for k in CATEGORIES} | {
    "mna": "M&A",
    "agm_egm": "AGM/EGM",
    "unclassified": "Compliance filing",
}
