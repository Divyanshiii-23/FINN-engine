"""The numbers path: reported cells from results filings, joined across filings,
and every derived metric computed in code with its formula and inputs.

Nothing here reads a transcript or a presentation, so a number management
says on a call can never become a reported actual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..fmt import cr
from . import periods as P
from .models import Doc, Fact
from .statements import Cell, Statements

FIELD_LABEL = {
    "revenue": "Revenue from operations",
    "interest_income": "Interest income",
    "other_income": "Other income",
    "total_income": "Total income",
    "materials": "Cost of materials consumed",
    "purchases": "Purchases of stock-in-trade",
    "inventory_change": "Changes in inventories",
    "employee": "Employee benefits expense",
    "finance_cost": "Finance costs",
    "impairment": "Impairment on financial instruments",
    "dna": "Depreciation and amortisation",
    "other_exp": "Other expenses",
    "total_exp": "Total expenses",
    "pbt_pre_exc": "Profit before exceptional items and tax",
    "exceptional": "Exceptional items",
    "pbt": "Profit before tax",
    "tax": "Tax expense",
    "pat": "Profit after tax",
    "total_assets": "Total assets",
    "total_eq_liab": "Total equity and liabilities",
    "total_equity": "Total equity",
    "borrowings": "Borrowings (all)",
    "cash": "Cash and cash equivalents",
    "bank_balances": "Other bank balances",
    "current_investments": "Current investments",
    "receivables": "Trade receivables",
    "inventories": "Inventories",
    "payables": "Trade payables",
    "loans": "Loans",
    "cfo": "Net cash from operating activities",
    "capex": "Purchase of property, plant and equipment",
    "capex_proceeds": "Proceeds from sale of property, plant and equipment",
    "cfi": "Net cash from investing activities",
    "cff": "Net cash from financing activities",
}


def fmt_val(v: float, unit: str) -> str:
    if unit == "cr":
        return f"-₹{cr(-v, 1)} cr" if v < 0 else f"₹{cr(v, 1)} cr"
    if unit == "pct":
        return f"{v * 100:.1f}%"
    if unit == "growth":
        return f"{v * 100:+.1f}%"
    if unit == "pp":
        return f"{v:+.1f} pp"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "multiple":
        return f"{v:.1f}x"
    if unit == "days":
        return f"{v:.0f} days"
    return f"{v:.2f}"


class Facts:
    """Registry of citable facts. IDs are stable and readable."""

    def __init__(self) -> None:
        self.items: dict[str, Fact] = {}

    def add(self, f: Fact) -> str:
        self.items.setdefault(f.id, f)
        return f.id

    def get(self, fid: str | None) -> Fact | None:
        return self.items.get(fid) if fid else None


@dataclass
class Val:
    value: float
    fact: str


def _pid(period: str) -> str:
    return period.replace(" ", "")


@dataclass
class Numbers:
    facts: Facts
    is_financial: bool
    q: dict[str, dict[str, tuple[Cell, Doc]]] = field(default_factory=dict)  # quarter -> field
    agg: dict[str, dict[str, tuple[Cell, Doc]]] = field(default_factory=dict)  # H1/9M/FY reported columns
    bs: dict[str, dict[str, tuple[Cell, Doc]]] = field(default_factory=dict)
    cf: dict[str, dict[str, tuple[Cell, Doc]]] = field(default_factory=dict)
    seg: dict[str, dict[str, tuple[Cell, Doc]]] = field(default_factory=dict)
    restated: list[dict] = field(default_factory=list)
    basis: str = "consolidated"
    checks: list[dict] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ build
    @classmethod
    def build(cls, facts: Facts, filings: list[tuple[Doc, Statements]], is_financial: bool) -> "Numbers":
        n = cls(facts=facts, is_financial=is_financial)
        usable = [(d, s) for d, s in filings if s.status in ("ok", "needs_review") and s.current]
        if not usable:
            return n
        # Newest filing first: later filings carry restatements of earlier quarters.
        usable.sort(key=lambda t: P.q_index(t[1].current or "Q1 FY00"), reverse=True)
        n.basis = usable[0][1].basis.get("P&L", "unknown")
        for doc, st in usable:
            if st.basis.get("P&L") not in (n.basis, "unknown"):
                n.checks.append({"check": f"basis matches ({doc.title})", "ok": False, "detail": f"{st.basis.get('P&L')} statement skipped; FINN uses {n.basis} figures"})
                continue
            n.checks.extend({**c, "doc": doc.id} for c in st.checks)
            n.labels.update(st.labels)
            for period, fields in st.pnl.items():
                target = n.q if period.startswith("Q") else n.agg
                bucket = target.setdefault(period, {})
                for k, cell in fields.items():
                    if k in bucket:
                        newer = bucket[k][0].value
                        if abs(newer - cell.value) > max(0.5, 0.005 * abs(newer)):
                            n.restated.append({"period": period, "field": k, "earlier": cell.value, "later": newer, "earlier_doc": doc.id, "later_doc": bucket[k][1].id})
                        continue
                    bucket[k] = (cell, doc)
            for target, src in ((n.bs, st.bs), (n.cf, st.cf), (n.seg, st.segments)):
                for period, fields in src.items():
                    bucket = target.setdefault(period, {})
                    for k, cell in fields.items():
                        bucket.setdefault(k, (cell, doc))
        return n

    # ------------------------------------------------------------ reported
    def _reported(self, store: dict, period: str, key: str, ns: str) -> Val | None:
        hit = store.get(period, {}).get(key)
        if not hit:
            return None
        cell, doc = hit
        fid = f"r:{ns}:{_pid(period)}:{key}"
        self.facts.add(Fact(
            id=fid, info_class="reported", label=f"{FIELD_LABEL.get(key) or self.labels.get(key, key)}, {period}", value=cell.value, unit="cr",
            display=fmt_val(cell.value, "cr"), period=period, basis=cell.basis, doc_id=doc.id, page=cell.page,
            section=cell.statement, row_text=cell.row_text, column=cell.column,
        ))
        return Val(cell.value, fid)

    def quarters(self) -> list[str]:
        return sorted((k for k in self.q if "revenue" in self.q[k]), key=P.q_index)

    def latest(self) -> str | None:
        qs = self.quarters()
        return qs[-1] if qs else None

    def flow(self, period: str, key: str) -> Val | None:
        """A P&L line for any period: reported if printed, else the sum of its quarters."""
        if period.startswith("Q"):
            return self._reported(self.q, period, key, "pl")
        hit = self._reported(self.agg, period, key, "pl")
        if hit:
            return hit
        parts = [self.flow(qq, key) for qq in P.quarters(period)]
        if not parts or any(p is None for p in parts):
            return None
        v = round(sum(p.value for p in parts), 2)  # type: ignore[union-attr]
        fid = f"c:{_pid(period)}:{key}"
        self.facts.add(Fact(
            id=fid, info_class="computed", label=f"{FIELD_LABEL.get(key) or self.labels.get(key, key)}, {period}", value=v, unit="cr", display=fmt_val(v, "cr"),
            period=period, basis=self.basis, formula=" + ".join(P.quarters(period)), inputs=[p.fact for p in parts],  # type: ignore[union-attr]
        ))
        return Val(v, fid)

    # ------------------------------------------------------------ derived
    def _computed(self, fid: str, label: str, v: float, unit: str, period: str | None, formula: str, inputs: list[str], note: str | None = None) -> Val:
        self.facts.add(Fact(id=fid, info_class="computed", label=label, value=v, unit=unit, display=fmt_val(v, unit), period=period, basis=self.basis, formula=formula, inputs=inputs, note=note))
        return Val(v, fid)

    def ebitda(self, period: str) -> Val | None:
        if self.is_financial:
            return None
        base, label = self.flow(period, "pbt_pre_exc"), "PBT before exceptional items"
        if not base:
            # Without a pre-exceptional line, PBT is only usable when there were no exceptional items;
            # the sign convention of that row varies, so FINN won't back it out.
            exc = self.flow(period, "exceptional")
            if exc and abs(exc.value) > 0:
                return None
            base, label = self.flow(period, "pbt"), "PBT (no exceptional items reported)"
        fc, dna, oi = self.flow(period, "finance_cost"), self.flow(period, "dna"), self.flow(period, "other_income")
        if not (base and fc and dna and oi):
            return None
        v = round(base.value + fc.value + dna.value - oi.value, 2)
        return self._computed(f"c:{_pid(period)}:ebitda", f"EBITDA, {period}", v, "cr", period,
                              f"{label} + finance costs + depreciation and amortisation - other income", [base.fact, fc.fact, dna.fact, oi.fact])

    def ebit(self, period: str) -> Val | None:
        e, d = self.ebitda(period), self.flow(period, "dna")
        if not (e and d):
            return None
        return self._computed(f"c:{_pid(period)}:ebit", f"EBIT, {period}", round(e.value - d.value, 2), "cr", period, "EBITDA - depreciation and amortisation", [e.fact, d.fact])

    def gross_profit(self, period: str) -> Val | None:
        rev, mat = self.flow(period, "revenue"), self.flow(period, "materials")
        if not (rev and mat) or self.is_financial:
            return None
        pur, inv = self.flow(period, "purchases"), self.flow(period, "inventory_change")
        v = rev.value - mat.value - (pur.value if pur else 0) - (inv.value if inv else 0)
        ins = [rev.fact, mat.fact] + [x.fact for x in (pur, inv) if x]
        return self._computed(f"c:{_pid(period)}:gross_profit", f"Gross profit, {period}", round(v, 2), "cr", period,
                              "Revenue - materials - purchases of stock-in-trade - change in inventories", ins)

    def nii(self, period: str) -> Val | None:
        ii = self.flow(period, "interest_income") or self.flow(period, "revenue")
        fc = self.flow(period, "finance_cost")
        if not (ii and fc):
            return None
        return self._computed(f"c:{_pid(period)}:nii", f"Net interest income, {period}", round(ii.value - fc.value, 2), "cr", period, "Interest income - finance costs", [ii.fact, fc.fact])

    def metric_amount(self, period: str, metric: str) -> Val | None:
        return {
            "revenue": lambda: self.flow(period, "revenue"),
            "pat": lambda: self.flow(period, "pat"),
            "pbt": lambda: self.flow(period, "pbt"),
            "ebitda": lambda: self.ebitda(period),
            "ebit": lambda: self.ebit(period),
            "gross_profit": lambda: self.gross_profit(period),
            "nii": lambda: self.nii(period),
            "impairment": lambda: self.flow(period, "impairment"),
        }[metric]()

    def margin(self, period: str, num: str) -> Val | None:
        a, r = self.metric_amount(period, num), self.flow(period, "revenue")
        if not (a and r and r.value):
            return None
        label = {"ebitda": "EBITDA margin", "ebit": "EBIT margin", "gross_profit": "Gross margin", "pat": "PAT margin"}[num]
        return self._computed(f"c:{_pid(period)}:{num}_margin", f"{label}, {period}", a.value / r.value, "pct", period,
                              f"{label.split(' margin')[0]} ÷ revenue (summed over the period, never an average of quarterly margins)", [a.fact, r.fact])

    def growth(self, period: str, metric: str, base: str | None = None) -> Val | None:
        base = base or (P.prev_q(period) if base == "qoq" else P.shift_year(period))
        a, b = self.metric_amount(period, metric), self.metric_amount(base, metric)
        if not (a and b) or b.value <= 0:
            return None
        kind = "QoQ" if P.parse(base) and P.parse(period) and P.parse(base)[1] == P.parse(period)[1] and len(P.quarters(base)) == 1 and base != P.shift_year(period) else "YoY"
        return self._computed(f"c:{_pid(period)}:{metric}_growth_{_pid(base)}", f"{metric.upper() if metric in ('pat', 'pbt', 'nii', 'ebitda', 'ebit') else metric.replace('_', ' ').capitalize()} growth, {period} vs {base}",
                              a.value / b.value - 1, "growth", period, f"{period} ÷ {base} - 1", [a.fact, b.fact])

    def qoq(self, period: str, metric: str) -> Val | None:
        return self.growth(period, metric, P.prev_q(period))

    def margin_change(self, period: str, base: str, num: str = "ebitda") -> Val | None:
        a, b = self.margin(period, num), self.margin(base, num)
        if not (a and b):
            return None
        return self._computed(f"c:{_pid(period)}:{num}_margin_chg_{_pid(base)}", f"{num.upper() if num != 'gross_profit' else 'Gross'} margin change, {period} vs {base}",
                              round((a.value - b.value) * 100, 2), "pp", period, f"margin {period} - margin {base}", [a.fact, b.fact])

    # ------------------------------------------------------------ balance sheet & cash
    def bs_val(self, asof: str, key: str) -> Val | None:
        return self._reported(self.bs, asof, key, "bs")

    def bs_dates(self) -> list[str]:
        return sorted(self.bs, key=P.sort_key)

    def net_debt(self, asof: str) -> Val | None:
        b = self.bs_val(asof, "borrowings")
        if not b:
            return None
        liquid = [x for x in (self.bs_val(asof, "cash"), self.bs_val(asof, "bank_balances"), self.bs_val(asof, "current_investments")) if x]
        if not liquid:
            return None
        v = round(b.value - sum(x.value for x in liquid), 2)
        return self._computed(f"c:bs:{_pid(asof)}:net_debt", f"Net debt, {asof} (negative = net cash)", v, "cr", asof,
                              "Borrowings - cash - other bank balances - current investments", [b.fact] + [x.fact for x in liquid])

    def debt_equity(self, asof: str) -> Val | None:
        b, e = self.bs_val(asof, "borrowings"), self.bs_val(asof, "total_equity")
        if not (b and e and e.value > 0):
            return None
        return self._computed(f"c:bs:{_pid(asof)}:de", f"Debt to equity, {asof}", round(b.value / e.value, 2), "x", asof, "Borrowings ÷ total equity", [b.fact, e.fact])

    def ttm(self, asof: str, metric: str = "revenue") -> Val | None:
        end = P.quarters(asof)[-1] if P.quarters(asof) else None
        if not end:
            return None
        qs = [P.prev_q(end, i) for i in range(3, -1, -1)]
        parts = [self.metric_amount(qq, metric) for qq in qs]
        if any(p is None for p in parts):
            return None
        v = round(sum(p.value for p in parts), 2)  # type: ignore[union-attr]
        return self._computed(f"c:ttm:{_pid(end)}:{metric}", f"{metric.capitalize() if metric != 'pat' else 'PAT'}, trailing twelve months to {end}", v, "cr", end, " + ".join(qs), [p.fact for p in parts])  # type: ignore[union-attr]

    def wc_days(self, asof: str) -> Val | None:
        rec, inv, pay = self.bs_val(asof, "receivables"), self.bs_val(asof, "inventories"), self.bs_val(asof, "payables")
        rev = self.ttm(asof)
        if not (rec and rev and rev.value):
            return None
        net = rec.value + (inv.value if inv else 0) - (pay.value if pay else 0)
        ins = [x.fact for x in (rec, inv, pay) if x] + [rev.fact]
        return self._computed(f"c:bs:{_pid(asof)}:wc_days", f"Working-capital days, {asof}", round(net / rev.value * 365, 1), "days", asof,
                              "(trade receivables + inventories - trade payables) ÷ trailing-twelve-month revenue × 365", ins)

    def receivable_days(self, asof: str) -> Val | None:
        rec, rev = self.bs_val(asof, "receivables"), self.ttm(asof)
        if not (rec and rev and rev.value):
            return None
        return self._computed(f"c:bs:{_pid(asof)}:rec_days", f"Receivable days, {asof}", round(rec.value / rev.value * 365, 1), "days", asof,
                              "Trade receivables ÷ trailing-twelve-month revenue × 365", [rec.fact, rev.fact])

    def cf_val(self, period: str, key: str) -> Val | None:
        return self._reported(self.cf, period, key, "cf")

    def cf_periods(self) -> list[str]:
        return sorted(self.cf, key=P.sort_key)

    def capex(self, period: str) -> Val | None:
        c = self.cf_val(period, "capex")
        if c:
            return self._computed(f"c:{_pid(period)}:capex", f"Capex, {period}", round(-c.value if c.value < 0 else c.value, 2), "cr", period,
                                  "Purchase of property, plant and equipment, as an outflow (sign flipped)", [c.fact])
        if P.parse(period) and P.parse(period)[0] == "H2":  # FY - H1
            fy = f"FY{period[-2:]}"
            a, b = self.capex(fy), self.capex(f"H1 FY{period[-2:]}")
            if a and b:
                return self._computed(f"c:{_pid(period)}:capex", f"Capex, {period}", round(a.value - b.value, 2), "cr", period, f"{fy} - H1", [a.fact, b.fact])
        return None

    def fcf(self, period: str) -> Val | None:
        o, c = self.cf_val(period, "cfo"), self.capex(period)
        if not (o and c):
            return None
        return self._computed(f"c:{_pid(period)}:fcf", f"Free cash flow, {period}", round(o.value - c.value, 2), "cr", period, "Operating cash flow - capex", [o.fact, c.fact])

    def ratio(self, fid: str, label: str, a: Val | None, b: Val | None, formula: str, period: str) -> Val | None:
        if not (a and b and b.value):
            return None
        return self._computed(fid, label, round(a.value / b.value, 3), "x", period, formula, [a.fact, b.fact])

    def avg_loans(self, period: str) -> tuple[Val, Val] | None:
        """Opening and closing loans for a fiscal YTD period (opening = previous March)."""
        p = P.parse(period)
        if not p:
            return None
        end = P.end_of(period)
        close_label = P.label_for_end(end, "ytd") if end else period
        open_, close = self.bs_val(f"FY{(p[1] - 1) % 100:02d}", "loans"), self.bs_val(close_label or period, "loans")
        return (open_, close) if open_ and close else None

    def credit_cost(self, period: str) -> Val | None:
        imp, ab = self.flow(period, "impairment"), self.avg_loans(period)
        if not (imp and ab):
            return None
        n = len(P.quarters(period))
        avg = (ab[0].value + ab[1].value) / 2
        return self._computed(f"c:{_pid(period)}:credit_cost", f"Credit cost, {period} (annualised)", round(imp.value * 4 / n / avg, 4), "pct", period,
                              f"impairment × 4/{n} ÷ average of opening and closing loans", [imp.fact, ab[0].fact, ab[1].fact],
                              note="On-book loans from the balance sheet; the company may quote credit cost on AUM.")

    def nim(self, period: str) -> Val | None:
        ni, ab = self.nii(period), self.avg_loans(period)
        if not (ni and ab):
            return None
        n = len(P.quarters(period))
        avg = (ab[0].value + ab[1].value) / 2
        return self._computed(f"c:{_pid(period)}:nim", f"Net interest margin on loans, {period} (annualised)", round(ni.value * 4 / n / avg, 4), "pct", period,
                              f"net interest income × 4/{n} ÷ average of opening and closing loans", [ni.fact, ab[0].fact, ab[1].fact],
                              note="Computed on on-book loans; companies often quote NIM on average AUM or earning assets.")

    def loan_growth_ytd(self, period: str) -> Val | None:
        ab = self.avg_loans(period)
        if not ab:
            return None
        return self._computed(f"c:{_pid(period)}:loan_growth_ytd", f"Loan book growth since March, {period}", ab[1].value / ab[0].value - 1, "growth", period,
                              "closing loans ÷ opening (March) loans - 1", [ab[1].fact, ab[0].fact])

    def segment_mix(self, quarter: str) -> list[tuple[str, Val, float]]:
        rows = self.seg.get(quarter, {})
        vals = [(name, self._reported(self.seg, quarter, name, "seg")) for name in rows]
        total = sum(v.value for _, v in vals if v)
        return [(name, v, v.value / total) for name, v in vals if v and total > 0]
