"""Typed records that flow through the pipeline.

Every announcement keeps its source references (exchange, id, URLs, fetch
time, raw payload location). Every derived value keeps the inputs it came
from, so the feed can show *why* something was ranked or computed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["bse", "nse"]
Dataset = Literal["live", "fixture"]


class Company(BaseModel):
    symbol: str  # NSE symbol
    name: str
    bse_code: str | None = None
    isin: str | None = None
    yahoo: str | None = None  # e.g. RELIANCE.NS
    sector: str | None = None
    is_financial: bool = False
    weight: float | None = None
    # Optional reference sizes for relative materiality (crore). When missing,
    # the size component is skipped and the reasoning says so.
    market_cap_cr: float | None = None
    revenue_ttm_cr: float | None = None

    @property
    def yahoo_symbol(self) -> str:
        return self.yahoo or f"{self.symbol}.NS"


class SourceRef(BaseModel):
    source: Source
    source_id: str
    listing_url: str | None = None  # exchange page for the company / filing
    attachment_url: str | None = None
    fetched_at: datetime
    raw_path: str | None = None  # where the raw payload is stored
    fixture: bool = False  # True only for synthetic test fixtures


class Announcement(BaseModel):
    id: str  # stable: sha1(source:source_id)
    symbol: str
    company_on_filing: str
    subject: str
    headline: str | None = None
    exchange_category: str | None = None
    exchange_subcategory: str | None = None
    filed_at: datetime  # exchange submission/dissemination time, tz-aware IST
    source: SourceRef
    attachment_size: int | None = None
    # Filled by de-duplication
    duplicate_of: str | None = None
    duplicates: list[str] = Field(default_factory=list)
    duplicate_reason: str | None = None
    supersedes: str | None = None  # a revised/corrigendum filing points at the original


class Classification(BaseModel):
    category: str
    subtype: str | None = None
    routine: bool
    method: Literal["rule", "fallback"] = "rule"
    rule_id: str | None = None
    matched: str | None = None  # text that triggered the rule
    confidence: Literal["high", "medium", "low"] = "high"


class Evidence(BaseModel):
    """Where a value came from."""

    kind: Literal["pdf_row", "filing_text", "computed", "eod_bar"]
    page: int | None = None
    text: str | None = None
    formula: str | None = None


class Figure(BaseModel):
    value: float | None
    evidence: Evidence | None = None


class ResultsRow(BaseModel):
    key: Literal["revenue", "ebitda", "pbt", "pat"]
    label: str
    current: Figure
    prev_q: Figure
    prev_y: Figure
    qoq: float | None = None
    yoy: float | None = None


class ResultsExtraction(BaseModel):
    status: Literal["ok", "needs_review", "failed", "unavailable"]
    reason: str | None = None
    basis: Literal["consolidated", "standalone", "unknown"] = "unknown"
    unit_detected: str | None = None
    period_label: str | None = None
    column_order: Literal["header_dates", "assumed_sebi_standard"] | None = None
    page: int | None = None
    rows: list[ResultsRow] = Field(default_factory=list)
    ebitda_formula: str | None = None
    margin: dict[str, float | None] | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    extractor_version: str | None = None


class Facts(BaseModel):
    amounts_cr: list[float] = Field(default_factory=list)
    amount_text: str | None = None
    rating_action: Literal["upgrade", "downgrade", "reaffirm", "withdrawn", "assigned", "outlook_change"] | None = None
    rating_from: str | None = None
    rating_to: str | None = None
    person: str | None = None
    role: str | None = None
    person_action: Literal["appointment", "resignation", "cessation", "retirement", "reappointment"] | None = None
    pledge_pct: float | None = None
    pledge_prev_pct: float | None = None
    record_date: str | None = None
    dividend_per_share: float | None = None
    call_date: str | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)  # management events with several filings


class MaterialityComponent(BaseModel):
    code: str
    label: str
    points: float
    detail: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class Materiality(BaseModel):
    score: int
    tier: Literal["interrupt", "brief", "routine"]
    raw_total: float
    components: list[MaterialityComponent]
    floor: str | None = None  # name of hard floor applied
    version: str


class Explanation(BaseModel):
    what: str
    why: str
    generator: str  # "template" or "llm:<model>"
    grounded: bool
    rejected_llm_reason: str | None = None


class EodBar(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float
    volume: int | None


class MarketSignal(BaseModel):
    symbol: str
    date: date
    close: float
    prev_close: float | None
    ret_1d: float | None  # from adjusted closes
    avg_vol_20d: float | None
    vol_ratio_20d: float | None
    ret_stdev_60d: float | None
    ret_z: float | None
    split_or_bonus_on_date: bool = False
    bars_used: int
    note: str | None = None


class Event(BaseModel):
    """One real-world development, possibly several filings."""

    id: str
    symbol: str
    category: str
    subtype: str | None
    routine: bool
    title: str
    first_filed_at: datetime
    last_filed_at: datetime
    announcements: list[Announcement]
    classification: Classification
    facts: Facts
    results: ResultsExtraction | None = None
    reaction: MarketSignal | None = None
    reaction_session: date | None = None
    materiality: Materiality | None = None
    explanation: Explanation | None = None
    attachment: dict[str, Any] | None = None  # {status, url, note, pages}
    fixture: bool = False


class FetchLog(BaseModel):
    source: str
    target: str
    url: str | None
    ok: bool
    status: int | None = None
    error: str | None = None
    fetched_at: datetime
    raw_path: str | None = None
    rows: int = 0
