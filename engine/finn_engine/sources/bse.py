"""BSE corporate announcements.

Endpoint and response fields verified against the recorded sample response
published with the open-source BseIndiaApi project: `Table` rows with NEWSID,
SCRIP_CD, NEWSSUB, HEADLINE, DT_TM, DissemDT, ATTACHMENTNAME, SUBCATNAME,
CATEGORYNAME, SLONGNAME, NSURL, Fld_Attachsize; `Table1[0].ROWCNT`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from ..models import Announcement, Company, FetchLog, SourceRef
from .http import HttpClient

API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"
IST = timezone(timedelta(hours=5, minutes=30))
HEADERS = {"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}


def fetch(client: HttpClient, company: Company, start: date, end: date, max_pages: int = 10) -> tuple[list[dict], list[FetchLog]]:
    """All announcement rows for one scrip in [start, end], following pagination."""
    if not company.bse_code:
        return [], [FetchLog(source="bse", target=company.symbol, url=None, ok=False, error="no BSE code configured", fetched_at=datetime.now(timezone.utc))]
    rows: list[dict] = []
    logs: list[FetchLog] = []
    for page in range(1, max_pages + 1):
        params = {
            "pageno": page,
            "strCat": "-1",
            "subcategory": "-1",
            "strPrevDate": start.strftime("%Y%m%d"),
            "strToDate": end.strftime("%Y%m%d"),
            "strSearch": "P",
            "strscrip": company.bse_code,
            "strType": "C",
        }
        data, log = client.get("bse", company.symbol, API, params=params, headers=HEADERS)
        if data is None or not isinstance(data, dict):
            logs.append(log)
            break
        table = data.get("Table") or []
        log.rows = len(table)
        logs.append(log)
        for r in table:
            r["_raw_path"] = log.raw_path
            r["_fetched_at"] = log.fetched_at.isoformat()
        rows.extend(table)
        total = (data.get("Table1") or [{}])[0].get("ROWCNT") or 0
        if not table or len(rows) >= int(total):
            break
    else:
        # Out of pages before the end of the list: the oldest announcements in the window are missing. Say so.
        logs.append(FetchLog(source="bse", target=f"{company.symbol} (truncated)", url=API, ok=False,
                             error=f"stopped after {max_pages} pages ({len(rows)} of {total} announcements); older filings in the window weren't fetched",
                             fetched_at=datetime.now(timezone.utc)))
    return rows, logs


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(\.\d+)?", s)
    if not m:
        return None
    return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}").replace(tzinfo=IST)


_STOP = {"ltd", "limited", "the", "and", "&", "co", "company", "inc", "india"}


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _STOP}


def name_matches(config_name: str, filing_name: str) -> bool:
    """Guard against a wrong scrip code: the filer's name must match the company."""
    a, b = _tokens(config_name), _tokens(filing_name)
    if not a or not b:
        return False
    return a <= b or len(a & b) / len(a | b) >= 0.5


def attachment_urls(name: str | None) -> list[str]:
    if not name:
        return []
    return [ATTACH_LIVE + name, ATTACH_HIS + name]


def to_announcements(rows: Iterable[dict[str, Any]], company: Company, fixture: bool = False) -> tuple[list[Announcement], list[str]]:
    """Normalise rows. Returns (announcements, rejection notes)."""
    out: list[Announcement] = []
    rejected: list[str] = []
    for r in rows:
        filer = (r.get("SLONGNAME") or "").strip()
        if filer and not name_matches(company.name, filer):
            rejected.append(f"BSE row {r.get('NEWSID')}: filer '{filer}' does not match {company.name}; check the BSE code")
            continue
        filed = parse_time(r.get("DissemDT")) or parse_time(r.get("DT_TM")) or parse_time(r.get("NEWS_DT"))
        if not filed:
            rejected.append(f"BSE row {r.get('NEWSID')}: no parseable timestamp")
            continue
        sid = str(r.get("NEWSID"))
        att = (r.get("ATTACHMENTNAME") or "").strip() or None
        fetched = r.get("_fetched_at")
        ref = SourceRef(
            source="bse",
            source_id=sid,
            listing_url=r.get("NSURL") if not fixture else None,
            attachment_url=(attachment_urls(att)[0] if att and not fixture else (f"fixture://{att}" if att else None)),
            fetched_at=datetime.fromisoformat(fetched) if fetched else datetime.now(timezone.utc),
            raw_path=r.get("_raw_path"),
            fixture=fixture,
        )
        out.append(
            Announcement(
                id=hashlib.sha1(f"bse:{sid}".encode()).hexdigest()[:16],
                symbol=company.symbol,
                company_on_filing=filer or company.name,
                subject=(r.get("NEWSSUB") or "").strip(),
                headline=(r.get("HEADLINE") or "").strip() or None,
                exchange_category=(r.get("CATEGORYNAME") or None),
                exchange_subcategory=(r.get("SUBCATNAME") or None),
                filed_at=filed,
                source=ref,
                attachment_size=r.get("Fld_Attachsize"),
            )
        )
    return out, rejected
