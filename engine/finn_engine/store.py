"""SQLite store. The SQL is kept portable (no SQLite-only features), but only SQLite is implemented and tested.

Idempotent: re-running a window upserts the same ids, so events accumulate
across runs without duplicates.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Announcement, EodBar, Event, FetchLog

SCHEMA = """
create table if not exists runs (
  id integer primary key autoincrement, dataset text not null, started_at text not null,
  finished_at text, window_start text, window_end text, summary text);
create table if not exists fetch_log (
  run_id integer, source text, target text, url text, ok integer, status integer,
  error text, fetched_at text, raw_path text, rows integer);
create table if not exists announcements (
  id text primary key, symbol text not null, source text not null, source_id text not null,
  filed_at text not null, duplicate_of text, body text not null);
create table if not exists events (
  id text primary key, symbol text not null, last_filed_at text not null, tier text, score integer,
  body text not null);
create index if not exists events_time on events(last_filed_at);
create table if not exists bars (
  symbol text not null, date text not null, body text not null, primary key (symbol, date));
create table if not exists splits (symbol text not null, date text not null, primary key (symbol, date));
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def start_run(self, dataset: str, start: date, end: date) -> int:
        cur = self.db.execute("insert into runs(dataset, started_at, window_start, window_end) values (?,?,?,?)", (dataset, datetime.now(timezone.utc).isoformat(), start.isoformat(), end.isoformat()))
        self.db.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, summary: dict) -> None:
        self.db.execute("update runs set finished_at=?, summary=? where id=?", (datetime.now(timezone.utc).isoformat(), json.dumps(summary), run_id))
        self.db.commit()

    def log(self, run_id: int, logs: list[FetchLog]) -> None:
        self.db.executemany(
            "insert into fetch_log values (?,?,?,?,?,?,?,?,?,?)",
            [(run_id, l.source, l.target, l.url, int(l.ok), l.status, l.error, l.fetched_at.isoformat(), l.raw_path, l.rows) for l in logs],
        )
        self.db.commit()

    def put_announcements(self, items: list[Announcement]) -> None:
        self.db.executemany(
            "insert into announcements values (?,?,?,?,?,?,?) on conflict(id) do update set duplicate_of=excluded.duplicate_of, body=excluded.body",
            [(a.id, a.symbol, a.source.source, a.source.source_id, a.filed_at.isoformat(), a.duplicate_of, a.model_dump_json()) for a in items],
        )
        self.db.commit()

    def put_events(self, events: list[Event]) -> None:
        self.db.executemany(
            "insert into events values (?,?,?,?,?,?) on conflict(id) do update set last_filed_at=excluded.last_filed_at, tier=excluded.tier, score=excluded.score, body=excluded.body",
            [(e.id, e.symbol, e.last_filed_at.isoformat(), e.materiality.tier if e.materiality else None, e.materiality.score if e.materiality else None, e.model_dump_json()) for e in events],
        )
        self.db.commit()

    def events_since(self, since: datetime) -> list[Event]:
        rows = self.db.execute("select body from events where last_filed_at >= ? order by last_filed_at desc", (since.isoformat(),)).fetchall()
        return [Event.model_validate_json(r[0]) for r in rows]

    def put_bars(self, symbol: str, bars: list[EodBar], splits: set[date]) -> None:
        self.db.executemany("insert or replace into bars values (?,?,?)", [(symbol, b.date.isoformat(), b.model_dump_json()) for b in bars])
        self.db.executemany("insert or ignore into splits values (?,?)", [(symbol, d.isoformat()) for d in splits])
        self.db.commit()

    def bars(self, symbol: str) -> tuple[list[EodBar], set[date]]:
        rows = self.db.execute("select body from bars where symbol=? order by date", (symbol,)).fetchall()
        sp = {date.fromisoformat(r[0]) for r in self.db.execute("select date from splits where symbol=?", (symbol,)).fetchall()}
        return [EodBar.model_validate_json(r[0]) for r in rows], sp
