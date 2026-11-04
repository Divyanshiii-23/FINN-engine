"""NSE corporate announcements (secondary source).

NSE requires session cookies from its homepage and commonly blocks cloud IPs.
The field mapping below (seq_id, desc, attchmntText, an_dt / sort_date,
attchmntFile, sm_name) follows NSE's public JSON as commonly documented; it is
NOT yet verified against a live response from this deployment (see docs).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any, Iterable

from ..models import Announcement, Company, FetchLog, SourceRef
from .bse import IST, name_matches
from .http import HttpClient

HOME = "https://www.nseindia.com/"
API = "https://www.nseindia.com/api/corporate-announcements"


def fetch(client: HttpClient, company: Company, start: date, end: date) -> tuple[list[dict], list[FetchLog]]:
    logs: list[FetchLog] = []
    # Cookie warm-up. A failure here is logged; the API call is still attempted.
    try:
        client.session.get(HOME, timeout=client.timeout_s)
    except Exception as e:  # noqa: BLE001
        logs.append(FetchLog(source="nse", target="cookie warm-up", url=HOME, ok=False, error=str(e)[:160], fetched_at=datetime.now(timezone.utc)))
    params = {"index": "equities", "symbol": company.symbol, "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y")}
    data, log = client.get("nse", company.symbol, API, params=params, headers={"Referer": HOME})
    rows = data if isinstance(data, list) else (data or {}).get("data", []) if isinstance(data, dict) else []
    log.rows = len(rows)
    for r in rows:
        r["_raw_path"] = log.raw_path
        r["_fetched_at"] = log.fetched_at.isoformat()
    logs.append(log)
    return rows, logs


def parse_time(r: dict[str, Any]) -> datetime | None:
    for key, fmt in (("sort_date", "%Y-%m-%d %H:%M:%S"), ("an_dt", "%d-%b-%Y %H:%M:%S"), ("exchdisstime", "%d-%b-%Y %H:%M:%S")):
        v = r.get(key)
        if v:
            try:
                return datetime.strptime(v.strip(), fmt).replace(tzinfo=IST)
            except ValueError:
                continue
    return None


def to_announcements(rows: Iterable[dict[str, Any]], company: Company, fixture: bool = False) -> tuple[list[Announcement], list[str]]:
    out: list[Announcement] = []
    rejected: list[str] = []
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        if sym and sym != company.symbol.upper():
            rejected.append(f"NSE row {r.get('seq_id')}: symbol {sym} is not {company.symbol}")
            continue
        filer = (r.get("sm_name") or "").strip()
        if filer and not name_matches(company.name, filer):
            rejected.append(f"NSE row {r.get('seq_id')}: filer '{filer}' does not match {company.name}")
            continue
        filed = parse_time(r)
        if not filed:
            rejected.append(f"NSE row {r.get('seq_id')}: no parseable timestamp")
            continue
        sid = str(r.get("seq_id") or hashlib.sha1(repr(sorted(r.items())).encode()).hexdigest()[:12])
        att = r.get("attchmntFile") or None
        fetched = r.get("_fetched_at")
        out.append(
            Announcement(
                id=hashlib.sha1(f"nse:{sid}".encode()).hexdigest()[:16],
                symbol=company.symbol,
                company_on_filing=filer or company.name,
                subject=(r.get("desc") or "").strip(),
                headline=(r.get("attchmntText") or "").strip() or None,
                exchange_category=None,
                exchange_subcategory=(r.get("desc") or None),
                filed_at=filed,
                source=SourceRef(
                    source="nse",
                    source_id=sid,
                    listing_url=None if fixture else f"https://www.nseindia.com/get-quotes/equity?symbol={company.symbol}",
                    attachment_url=(f"fixture://{att}" if fixture and att else att),
                    fetched_at=datetime.fromisoformat(fetched) if fetched else datetime.now(timezone.utc),
                    raw_path=r.get("_raw_path"),
                    fixture=fixture,
                ),
            )
        )
    return out, rejected
