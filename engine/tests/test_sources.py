import json

from finn_engine.models import Company
from finn_engine.sources import bse, nse
from finn_engine.sources.files import load_eod


def row(**kw):
    base = {
        "NEWSID": "abc", "SCRIP_CD": 990199, "NEWSSUB": "TEST COMPANY LTD - 990199 - Dividend", "DT_TM": "2026-11-03T17:30:12.95",
        "DissemDT": "2026-11-03T17:30:14.1", "HEADLINE": "Interim dividend", "SUBCATNAME": "Dividend", "CATEGORYNAME": None,
        "ATTACHMENTNAME": "a1b2.pdf", "Fld_Attachsize": 1234, "SLONGNAME": "TEST COMPANY LTD.", "NSURL": "https://www.bseindia.com/stock-share-price/x/",
    }
    base.update(kw)
    return base


def test_bse_row_normalises_with_source_refs_and_ist_time():
    c = Company(symbol="TEST", name="Test Company", bse_code="990199")
    out, rej = bse.to_announcements([row()], c)
    a = out[0]
    assert not rej
    assert a.filed_at.isoformat() == "2026-11-03T17:30:14+05:30"  # dissemination time, IST
    assert a.source.source == "bse" and a.source.source_id == "abc"
    assert a.source.attachment_url == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/a1b2.pdf"
    assert a.source.listing_url.startswith("https://www.bseindia.com/")


def test_wrong_scrip_code_is_rejected_by_name_guard():
    c = Company(symbol="TEST", name="Test Company", bse_code="990199")
    out, rej = bse.to_announcements([row(SLONGNAME="SOMEONE ELSE LTD.")], c)
    assert out == [] and "does not match" in rej[0]


def test_fixture_rows_never_get_real_exchange_urls():
    c = Company(symbol="TEST", name="Test Company", bse_code="990199")
    a = bse.to_announcements([row()], c, fixture=True)[0][0]
    assert a.source.fixture and a.source.listing_url is None and a.source.attachment_url.startswith("fixture://")


def test_name_matching():
    assert bse.name_matches("The Indian Hotels Company", "THE INDIAN HOTELS CO.LTD.")
    assert bse.name_matches("Larsen & Toubro", "LARSEN & TOUBRO LTD.")
    assert not bse.name_matches("Tata Steel", "TATA MOTORS LTD.")


def test_nse_rows_normalise():
    c = Company(symbol="TEST", name="Test Company")
    out, rej = nse.to_announcements([{"symbol": "TEST", "seq_id": "9", "desc": "Financial Results", "sort_date": "2026-11-03 19:14:05", "attchmntFile": "https://nsearchives.nseindia.com/x.pdf", "sm_name": "Test Company Limited"}], c)
    assert not rej and out[0].filed_at.hour == 19 and out[0].source.source == "nse"


def test_yfinance_csv_import(tmp_path):
    p = tmp_path / "X.csv"
    p.write_text("Date,Open,High,Low,Close,Adj Close,Volume\n2026-11-02,10,11,9,10.5,10.4,1000\n2026-11-03,10.5,11,10,10.8,10.7,1500\n")
    bars, splits = load_eod(p)
    assert [b.date.isoformat() for b in bars] == ["2026-11-02", "2026-11-03"] and bars[1].adj_close == 10.7 and bars[1].volume == 1500


def test_yahoo_chart_json_import(tmp_path):
    data = {"chart": {"result": [{"timestamp": [1793606400, 1793692800], "indicators": {"quote": [{"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [10.0, None], "volume": [5, 6]}], "adjclose": [{"adjclose": [9.9, None]}]}, "events": {"splits": {"1": {"date": 1793606400}}}}]}}
    p = tmp_path / "X.json"
    p.write_text(json.dumps(data))
    bars, splits = load_eod(p)
    assert len(bars) == 1 and bars[0].adj_close == 9.9 and len(splits) == 1  # missing session skipped
