"""Where Pull research gets its documents. Primary sources only.

Live:
  * NSE equity master (EQUITY_L.csv) to validate the ticker and get its ISIN;
    NSE quote meta-info as a fallback;
  * BSE scrip list (ListofScripData) to map ISIN → BSE code and industry;
  * BSE corporate announcements for the scrip, which carry the results
    filings, earnings-call transcripts, investor presentations, press
    releases and the annual report (all filed under SEBI LODR);
  * NSE annual-reports API for the annual report PDF;
  * documents the user adds from the company's IR site (--doc).

Files: the same payloads saved to a directory (see FileInputs), which is how
the synthetic fixtures and any manually exported data are read.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from ..models import Company, FetchLog
from ..sources import bse as bse_src
from ..sources import nse as nse_src
from ..sources.http import EXCHANGE_HOSTS, HttpClient

SEED_MASTER = Path(__file__).parent / "seed" / "nse_equity_list_2023-11-05.csv"
SEED_LABEL = "NSE equity list, seed copy dated 5 Nov 2023 (NSE couldn't be reached)"

NSE_MASTER = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_HOME = "https://www.nseindia.com/"
NSE_META = "https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
NSE_AR = "https://www.nseindia.com/api/annual-reports"
BSE_SCRIPS = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchInputs(Protocol):
    dataset: str

    def equity_master(self) -> tuple[list[dict], FetchLog]: ...
    def nse_meta(self, symbol: str) -> tuple[dict | None, FetchLog]: ...
    def bse_scrips(self) -> tuple[list[dict], FetchLog]: ...
    def announcements(self, bse_code: str, name: str, start: date, end: date) -> tuple[list[dict], list[FetchLog]]: ...
    def nse_announcements(self, symbol: str, name: str, start: date, end: date) -> tuple[list[dict], list[FetchLog]]: ...
    def annual_reports(self, symbol: str) -> tuple[list[dict], FetchLog]: ...
    def ir_documents(self, symbol: str) -> list[dict]: ...
    def download(self, ref: str, trusted: bool = False) -> tuple[bytes | None, FetchLog]: ...


def parse_master(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


class LiveInputs:
    dataset = "live"

    def __init__(self, client: HttpClient, cache: Path, extra_docs: list[dict] | None = None):
        self.c = client
        self.cache = cache
        self.extra = extra_docs or []
        cache.mkdir(parents=True, exist_ok=True)

    def _cached(self, name: str) -> Path | None:
        p = self.cache / name
        if p.exists() and datetime.fromtimestamp(p.stat().st_mtime).date() == date.today():
            return p
        return None

    def equity_master(self):
        p = self._cached("EQUITY_L.csv")
        if p:
            return parse_master(p.read_text()), FetchLog(source="nse", target="equity master (cached today)", url=NSE_MASTER, ok=True, fetched_at=_now(), raw_path=str(p))
        body, log = self.c.get("nse", "equity master", NSE_MASTER, headers={"Referer": NSE_HOME}, expect="bytes")
        if body is None:
            stale = self.cache / "EQUITY_L.csv"
            if stale.exists():
                log.error = (log.error or "") + "; using an older cached copy"
                return parse_master(stale.read_text()), log
            rows = parse_master(SEED_MASTER.read_text())
            log.error = (log.error or "") + "; using the bundled seed copy"
            log.target = SEED_LABEL
            log.rows = len(rows)
            return rows, log
        (self.cache / "EQUITY_L.csv").write_bytes(body)
        rows = parse_master(body.decode("utf-8", "replace"))
        log.rows = len(rows)
        return rows, log

    def nse_meta(self, symbol):
        try:
            self.c.session.get(NSE_HOME, timeout=self.c.timeout_s)
        except Exception:  # noqa: BLE001
            pass
        data, log = self.c.get("nse", symbol, NSE_META, params={"functionName": "getMetaData", "symbol": symbol}, headers={"Referer": NSE_HOME})
        return (data if isinstance(data, dict) and data.get("symbol") else None), log

    def bse_scrips(self):
        p = self._cached("bse_scrips.json")
        if p:
            return json.loads(p.read_text()), FetchLog(source="bse", target="scrip list (cached today)", url=BSE_SCRIPS, ok=True, fetched_at=_now(), raw_path=str(p))
        params = {"Group": "", "Scripcode": "", "industry": "", "segment": "Equity", "status": "Active"}
        data, log = self.c.get("bse", "scrip list", BSE_SCRIPS, params=params, headers=bse_src.HEADERS)
        rows = data if isinstance(data, list) else []
        if rows:
            (self.cache / "bse_scrips.json").write_text(json.dumps(rows))
        else:
            stale = self.cache / "bse_scrips.json"
            if stale.exists():
                # An older copy still maps ISIN to BSE code and industry; say how old it is.
                day = datetime.fromtimestamp(stale.stat().st_mtime).date().isoformat()
                rows = json.loads(stale.read_text())
                log = FetchLog(source="bse", target=f"scrip list (cached copy from {day}; live fetch failed: {log.error})", url=BSE_SCRIPS, ok=True,
                               rows=len(rows), fetched_at=_now(), raw_path=str(stale))
                return rows, log
        log.rows = len(rows)
        return rows, log

    def announcements(self, bse_code, name, start, end):
        comp = Company(symbol=bse_code, name=name, bse_code=bse_code)
        return bse_src.fetch(self.c, comp, start, end, max_pages=25)

    def nse_announcements(self, symbol, name, start, end):
        return nse_src.fetch(self.c, Company(symbol=symbol, name=name), start, end)

    def annual_reports(self, symbol):
        data, log = self.c.get("nse", symbol, NSE_AR, params={"index": "equities", "symbol": symbol}, headers={"Referer": NSE_HOME})
        rows = (data or {}).get("data", []) if isinstance(data, dict) else []
        log.rows = len(rows)
        return rows, log

    def ir_documents(self, symbol):
        return [d for d in self.extra if d.get("symbol", symbol).upper() == symbol]

    def download(self, ref, trusted=False):
        """`trusted` refs come from the operator (documents passed on the command line);
        everything else comes from exchange payloads and may only name an exchange host."""
        local = ref.startswith("file://") or (not ref.startswith(("http://", "https://")) and ("/" in ref or "\\" in ref))
        if local:
            if not trusted:
                return None, FetchLog(source="research", target=ref[:80], url=None, ok=False, error="local paths are only read for documents you supply", fetched_at=_now())
            p = Path(ref.removeprefix("file://"))
            ok = p.is_file()
            return (p.read_bytes() if ok else None), FetchLog(source="file", target=p.name, url=str(p), ok=ok, error=None if ok else "file not found", fetched_at=_now(), raw_path=str(p) if ok else None)
        urls = bse_src.attachment_urls(ref) if not ref.startswith("http") else [ref]
        hosts = None if trusted else EXCHANGE_HOSTS
        log = None
        for u in urls:
            body, log = self.c.get("research", ref[:120], u, headers=bse_src.HEADERS if "bseindia" in u else {"Referer": NSE_HOME}, expect="bytes", hosts=hosts)
            if body:
                return body, log
        return None, log or FetchLog(source="research", target=ref, url=None, ok=False, error="no URL", fetched_at=_now())


class FileInputs:
    """A directory with the same payloads the live sources return.

    nse/EQUITY_L.csv            NSE equity master
    bse/scrips.json             BSE ListofScripData rows
    bse/announcements/<code>.json   {"Table": [...]} as returned by AnnSubCategoryGetData
    nse/announcements/<SYMBOL>.json   [...] as returned by /api/corporate-announcements
    nse/annual_reports/<SYMBOL>.json  {"data": [...]} as returned by /api/annual-reports
    ir/<SYMBOL>.json            [{"kind", "period", "title", "file"}] documents from the company's IR site
    attachments/<file>          PDFs referenced by the above
    """

    def __init__(self, root: Path, extra_docs: list[dict] | None = None):
        self.root = root
        self.extra = extra_docs or []
        marker = root / "FIXTURE"
        self.fixture = marker.exists()
        self.dataset = "fixture" if self.fixture else "files"

    def _log(self, source: str, target: str, path: Path, ok: bool, rows: int = 0, error: str | None = None) -> FetchLog:
        return FetchLog(source=source, target=target, url=f"file://{path}", ok=ok, rows=rows, error=error, fetched_at=_now(), raw_path=str(path) if ok else None)

    def equity_master(self):
        p = self.root / "nse" / "EQUITY_L.csv"
        if not p.exists():
            return [], self._log("nse", "equity master", p, False, error="file not found")
        rows = parse_master(p.read_text())
        return rows, self._log("nse", "equity master", p, True, len(rows))

    def nse_meta(self, symbol):
        p = self.root / "nse" / "meta" / f"{symbol}.json"
        if not p.exists():
            return None, self._log("nse", symbol, p, False, error="no meta file")
        return json.loads(p.read_text()), self._log("nse", symbol, p, True, 1)

    def bse_scrips(self):
        p = self.root / "bse" / "scrips.json"
        if not p.exists():
            return [], self._log("bse", "scrip list", p, False, error="file not found")
        rows = json.loads(p.read_text())
        return rows, self._log("bse", "scrip list", p, True, len(rows))

    def announcements(self, bse_code, name, start, end):
        p = self.root / "bse" / "announcements" / f"{bse_code}.json"
        if not p.exists():
            return [], [self._log("bse", bse_code, p, False, error="no announcements file for this scrip")]
        data = json.loads(p.read_text())
        rows = data.get("Table", []) if isinstance(data, dict) else data
        for r in rows:
            r["_raw_path"] = str(p)
            r["_fetched_at"] = _now().isoformat()
        keep = []
        for r in rows:
            t = bse_src.parse_time(r.get("DissemDT")) or bse_src.parse_time(r.get("DT_TM"))
            if t and start <= t.date() <= end:
                keep.append(r)
        return keep, [self._log("bse", bse_code, p, True, len(keep))]

    def nse_announcements(self, symbol, name, start, end):
        p = self.root / "nse" / "announcements" / f"{symbol}.json"
        if not p.exists():
            return [], [self._log("nse", symbol, p, False, error="no NSE announcements file for this symbol")]
        data = json.loads(p.read_text())
        rows = data if isinstance(data, list) else data.get("data", [])
        keep = []
        for r in rows:
            t = nse_src.parse_time(r)
            if t and start <= t.date() <= end:
                keep.append({**r, "_raw_path": str(p), "_fetched_at": _now().isoformat()})
        return keep, [self._log("nse", symbol, p, True, len(keep))]

    def annual_reports(self, symbol):
        p = self.root / "nse" / "annual_reports" / f"{symbol}.json"
        if not p.exists():
            return [], self._log("nse", f"{symbol} annual reports", p, False, error="no annual-reports file")
        rows = json.loads(p.read_text()).get("data", [])
        return rows, self._log("nse", f"{symbol} annual reports", p, True, len(rows))

    def ir_documents(self, symbol):
        p = self.root / "ir" / f"{symbol}.json"
        docs = json.loads(p.read_text()) if p.exists() else []
        return docs + [d for d in self.extra if d.get("symbol", symbol).upper() == symbol]

    def download(self, ref, trusted=False):
        name = ref.removeprefix("fixture://").rsplit("/", 1)[-1]
        p = Path(ref) if (trusted and Path(ref).is_absolute()) else self.root / "attachments" / name
        if not p.exists():
            return None, self._log("file", name, p, False, error="attachment not in the input directory")
        return p.read_bytes(), self._log("file", name, p, True, 1)
