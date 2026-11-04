"""Typed records for Pull research. Every displayed item resolves to a Fact."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

InfoClass = Literal["reported", "guidance", "assertion", "outlook", "computed", "generated"]
DocKind = Literal["results", "transcript", "presentation", "annual_report", "press_release"]


class Identity(BaseModel):
    symbol: str
    name: str
    isin: str | None = None
    series: str | None = None
    listed_on: str | None = None
    bse_code: str | None = None
    bse_name: str | None = None
    industry: str | None = None
    market_cap_cr: float | None = None
    is_financial: bool = False
    is_it_services: bool = False
    sources: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Doc(BaseModel):
    id: str
    kind: DocKind
    title: str
    period: str | None = None
    period_basis: str | None = None  # how the period was decided
    filed_at: datetime | None = None
    source: str  # bse | nse | company_ir | fixture
    source_id: str | None = None
    url: str | None = None
    listing_url: str | None = None
    fetched_at: datetime | None = None
    raw_path: str | None = None
    sha256: str | None = None
    pages: int | None = None
    status: Literal["parsed", "unavailable", "failed", "not_used"] = "unavailable"
    status_reason: str | None = None
    fixture: bool = False
    parse: dict = Field(default_factory=dict)  # basis, unit, turns, roster size ...


class Fact(BaseModel):
    """One citable item. Numbers carry unit and display text; quotes carry location."""

    id: str
    info_class: InfoClass
    label: str
    value: float | None = None
    unit: str | None = None  # cr | pct | pp | x | days | ratio
    display: str | None = None
    period: str | None = None
    basis: str | None = None  # consolidated | standalone
    doc_id: str | None = None
    page: int | None = None
    section: str | None = None  # "Prepared remarks" | "Q&A" | statement name
    speaker: str | None = None
    role: str | None = None
    quote: str | None = None
    row_text: str | None = None
    column: str | None = None
    formula: str | None = None
    inputs: list[str] = Field(default_factory=list)
    note: str | None = None


class Target(BaseModel):
    kind: Literal["range", "point", "floor", "ceiling", "delta", "multiple", "direction", "words"]
    low: float | None = None
    high: float | None = None
    unit: str | None = None  # pct | pp | cr | x | bps
    direction: Literal["up", "down", "flat"] | None = None
    base_period: str | None = None
    text: str
    reading: str  # how FINN read the phrase, shown to the user


class Claim(BaseModel):
    id: str
    kind: Literal["guidance", "assertion", "outlook"]
    metric: str | None = None
    metric_label: str | None = None
    segment: str | None = None
    quote: str
    doc_id: str
    doc_kind: DocKind
    call_period: str | None = None
    page: int | None = None
    section: str | None = None
    speaker: str | None = None
    role: str = "management"
    target: Target | None = None
    period_text: str | None = None
    period: str | None = None
    hedge: Literal["firm", "expected", "aspirational", "conditional"] | None = None
    reaffirms: bool = False
    withdraws: bool = False
    confirmed_analyst_figure: bool = False
    context_quote: str | None = None
    basis_hint: Literal["yoy", "qoq"] | None = None
    theme: str | None = None
    tone: Literal["positive", "negative", "neutral"] = "neutral"
    method: str = "rules"
    gates: dict = Field(default_factory=dict)
    fact_id: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def explicit(self) -> bool:
        """Explicit guidance states a number; directional and words-only statements are qualitative."""
        return self.kind == "guidance" and self.target is not None and self.target.kind not in ("direction", "words")


class HistoryItem(BaseModel):
    call: str | None
    doc_id: str
    claim_id: str | None
    change: Literal["first", "also stated", "differs", "reiterated", "raised", "lowered", "changed", "withdrawn", "not repeated", "softened"]
    target: str | None = None
    fact_id: str | None = None
    date: str | None = None  # when it was said: the call date for transcripts, the filing date otherwise
    band: dict | None = None  # {"kind", "low", "high", "unit"} in the target's own units (percent, crore, pp)


class LedgerEntry(BaseModel):
    id: str
    kind: Literal["guidance", "assertion"]
    metric: str
    metric_label: str
    segment: str | None = None
    period: str | None = None
    target: str | None = None
    reading: str | None = None
    hedge: str | None = None
    explicit: bool = True  # a number was stated; False for directional or words-only statements
    better: str = "up"
    target_kind: str | None = None
    verdict: Literal[
        "delivered", "ahead", "missed", "pending", "dropped", "unverifiable", "consistent", "contradicted", "partial"
    ]
    status_note: str | None = None  # "on track" | "at risk" ...
    detail: str
    severity: int = 0
    actual_fact: str | None = None
    required_fact: str | None = None
    evidence: list[str] = Field(default_factory=list)
    history: list[HistoryItem] = Field(default_factory=list)


class Shift(BaseModel):
    id: str
    theme: str
    from_call: str | None
    to_call: str | None
    from_tone: str
    to_tone: str
    detail: str
    evidence: list[str]


class Point(BaseModel):
    """A sentence of FINN interpretation. Numbers in it come from the cited facts."""

    id: str
    text: str
    evidence: list[str]
    rule: str
    severity: int = 0
    implication: str | None = None


class Gap(BaseModel):
    area: str
    detail: str
