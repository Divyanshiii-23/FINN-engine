from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from finn_engine import fixtures as fx
from finn_engine.config import ENGINE_DIR, load
from finn_engine.export import build_feed
from finn_engine.models import Announcement, Company, SourceRef
from finn_engine.pipeline import FileInputs, run
from finn_engine.store import Store

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(scope="session")
def fixture_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("fx")
    fx.build(ENGINE_DIR, root / "inputs")
    cfg = load(ENGINE_DIR / "fixtures" / "universe.yaml")
    store = Store(root / "t.db")
    res = run(cfg, FileInputs(root / "inputs", fixture=True), store, fx.FIXTURE_FROM, fx.FIXTURE_TO, "fixture", use_llm=False)
    feed = build_feed(cfg, store, res, "fixture", as_of=fx.as_of())
    return cfg, res, feed, root


def ann(subject: str, headline: str | None = None, *, symbol="TEST", source="bse", sid="1", at="2026-11-03T19:00:00", attachment: str | None = None, size: int | None = None) -> Announcement:
    return Announcement(
        id=f"{source}-{sid}",
        symbol=symbol,
        company_on_filing="Test Co",
        subject=subject,
        headline=headline,
        filed_at=datetime.fromisoformat(at).replace(tzinfo=IST),
        source=SourceRef(source=source, source_id=sid, attachment_url=attachment, fetched_at=datetime.now(timezone.utc)),
        attachment_size=size,
    )


@pytest.fixture
def company() -> Company:
    return Company(symbol="TEST", name="Test Company", bse_code="990199")
