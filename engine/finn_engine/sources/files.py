"""File importers, for when the network is unavailable or data is provided by hand.

- BSE announcements JSON: the raw API response ({"Table": [...]}) or a list of rows.
- NSE announcements JSON: a list of rows or {"data": [...]}.
- EOD CSV: yfinance/Yahoo download format (Date,Open,High,Low,Close,Adj Close,Volume).
- Yahoo chart JSON: the raw chart endpoint response.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from ..models import EodBar
from .yahoo import parse_chart


def load_bse_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    rows = data.get("Table", []) if isinstance(data, dict) else data
    for r in rows:
        r.setdefault("_raw_path", str(path))
        r.setdefault("_fetched_at", datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat())
    return rows


def load_nse_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    rows = data.get("data", []) if isinstance(data, dict) else data
    for r in rows:
        r.setdefault("_raw_path", str(path))
        r.setdefault("_fetched_at", datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat())
    return rows


def load_eod(path: Path) -> tuple[list[EodBar], set[date]]:
    if path.suffix.lower() == ".json":
        return parse_chart(json.loads(path.read_text()))
    bars: list[EodBar] = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            close = row.get("Close")
            if not close or close.lower() in {"null", "nan", ""}:
                continue
            adj = row.get("Adj Close") or close
            num = lambda k: float(row[k]) if row.get(k) not in (None, "", "null") else None  # noqa: E731
            bars.append(
                EodBar(
                    date=date.fromisoformat(row["Date"][:10]),
                    open=num("Open"),
                    high=num("High"),
                    low=num("Low"),
                    close=float(close),
                    adj_close=float(adj),
                    volume=int(float(row["Volume"])) if row.get("Volume") else None,
                )
            )
    bars.sort(key=lambda b: b.date)
    return bars, set()
