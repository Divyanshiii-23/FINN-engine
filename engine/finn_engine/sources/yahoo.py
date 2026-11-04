"""End-of-day prices from Yahoo Finance's chart endpoint (as used by yfinance).

Returns raw closes and adjusted closes plus split events, so returns can be
computed on adjusted prices and split days can be flagged instead of raising a
false price alert.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..models import EodBar, FetchLog
from .http import HttpClient

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
IST = timezone(timedelta(hours=5, minutes=30))


def fetch(client: HttpClient, yahoo_symbol: str, range_: str = "6mo") -> tuple[dict | None, FetchLog]:
    return client.get(
        "yahoo",
        yahoo_symbol,
        CHART.format(symbol=yahoo_symbol),
        params={"range": range_, "interval": "1d", "events": "div,split", "includeAdjustedClose": "true"},
    )


def parse_chart(data: dict) -> tuple[list[EodBar], set[date]]:
    """Bars sorted by date, and the set of dates with a split event."""
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = (data.get("chart") or {}).get("error")
        raise ValueError(f"no chart result: {err}")
    r = result[0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    adj = (r.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or q.get("close")
    bars: list[EodBar] = []
    for i, t in enumerate(ts):
        close = (q.get("close") or [None])[i]
        if close is None:
            continue  # missing session (holiday, halt)
        d = datetime.fromtimestamp(t, tz=IST).date()
        bars.append(
            EodBar(
                date=d,
                open=(q.get("open") or [None])[i],
                high=(q.get("high") or [None])[i],
                low=(q.get("low") or [None])[i],
                close=float(close),
                adj_close=float(adj[i]) if adj and adj[i] is not None else float(close),
                volume=int((q.get("volume") or [0])[i] or 0),
            )
        )
    splits = {
        datetime.fromtimestamp(int(s["date"]), tz=IST).date()
        for s in ((r.get("events") or {}).get("splits") or {}).values()
        if "date" in s
    }
    bars.sort(key=lambda b: b.date)
    # Keep one bar per date (Yahoo occasionally repeats the live session).
    dedup: dict[date, EodBar] = {b.date: b for b in bars}
    return list(dedup.values()), splits
