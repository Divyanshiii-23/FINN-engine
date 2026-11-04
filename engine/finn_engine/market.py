"""Unusual price and volume detection from historical end-of-day bars.

Definitions (all deterministic):
- ret_1d: adjusted close / previous adjusted close - 1. Adjusted closes keep a
  split or bonus from looking like a crash.
- vol_ratio_20d: today's volume / mean volume of the previous 20 sessions
  (today excluded). Needs at least 15 prior sessions.
- ret_z: ret_1d / standard deviation of the previous 60 daily returns. Lets
  "unusual" be judged against the stock's own volatility. Needs 30 returns.
- A split or bonus on the day is flagged; price alerts are suppressed for it.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, time, timedelta, timezone

from .models import EodBar, MarketSignal

IST = timezone(timedelta(hours=5, minutes=30))
CLOSE = time(15, 30)


def signal_at(symbol: str, bars: list[EodBar], splits: set[date], on: date | None = None) -> MarketSignal | None:
    if not bars:
        return None
    idx = len(bars) - 1 if on is None else next((i for i, b in enumerate(bars) if b.date == on), None)
    if idx is None:
        return None
    b = bars[idx]
    prev = bars[idx - 1] if idx >= 1 else None
    ret = (b.adj_close / prev.adj_close - 1) if prev and prev.adj_close else None
    window = bars[max(0, idx - 20):idx]
    # After a split or bonus the share count changes, so volumes before it aren't comparable: restart the baseline.
    recent_split = max((i for i, x in enumerate(window) if x.date in splits), default=None)
    if recent_split is not None:
        window = window[recent_split:]
    # Zero-volume sessions are suspensions or data gaps, not quiet trading; they would shrink the baseline.
    vols = [x.volume for x in window if x.volume]
    avg_vol = statistics.fmean(vols) if len(vols) >= 15 else None
    vol_ratio = (b.volume / avg_vol) if avg_vol and b.volume is not None and avg_vol > 0 else None
    rets = [
        bars[i].adj_close / bars[i - 1].adj_close - 1
        for i in range(max(1, idx - 60), idx)
        if bars[i - 1].adj_close
    ]
    sd = statistics.stdev(rets) if len(rets) >= 30 else None
    z = (ret / sd) if ret is not None and sd else None
    notes = []
    if avg_vol is None:
        notes.append(f"volume baseline needs 15 prior sessions with trading; {len(vols)} available" + (" since the split or bonus" if recent_split is not None else ""))
    if sd is None:
        notes.append(f"volatility baseline needs 30 prior returns; {len(rets)} available")
    return MarketSignal(
        symbol=symbol,
        date=b.date,
        close=b.close,
        prev_close=prev.close if prev else None,
        ret_1d=ret,
        avg_vol_20d=avg_vol,
        vol_ratio_20d=vol_ratio,
        ret_stdev_60d=sd,
        ret_z=z,
        split_or_bonus_on_date=b.date in splits,
        bars_used=idx + 1,
        note="; ".join(notes) or None,
    )


def reaction_session(filed_at: datetime, bars: list[EodBar]) -> date | None:
    """The first session whose close comes after the filing (None if not yet in the data)."""
    local = filed_at.astimezone(IST)
    for b in bars:
        close_dt = datetime.combine(b.date, CLOSE, tzinfo=IST)
        if close_dt >= local:
            return b.date
    return None


def explaining_window(session: date, bars: list[EodBar]) -> tuple[datetime, datetime]:
    """Filings in (previous session close, this session close] can explain this session's move."""
    dates = [b.date for b in bars]
    i = dates.index(session)
    start_day = dates[i - 1] if i >= 1 else session - timedelta(days=1)
    return datetime.combine(start_day, CLOSE, tzinfo=IST), datetime.combine(session, CLOSE, tzinfo=IST)
