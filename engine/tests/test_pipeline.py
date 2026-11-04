"""End-to-end checks on the synthetic fixture dataset, including the integrity rules."""

from datetime import datetime


def by_symbol(feed, sym, cat=None):
    return [e for e in feed["events"] if e["symbol"] == sym and (cat is None or e["category"] == cat)]


def test_feed_is_labelled_fixture_everywhere(fixture_run):
    _, _, feed, _ = fixture_run
    assert feed["dataset"] == "fixture" and "not real exchange filings" in feed["dataset_note"]
    for e in feed["events"]:
        assert e["fixture"] is True
        for a in e["announcements"]:
            assert a["source"]["fixture"] is True
            assert a["source"]["listing_url"] is None
            url = a["source"]["attachment_url"]
            assert url is None or url.startswith("fixture://")


def test_every_event_has_sources_timestamps_and_reasoning(fixture_run):
    _, _, feed, _ = fixture_run
    for e in feed["events"]:
        assert e["announcements"], e["id"]
        for a in e["announcements"]:
            assert a["source"]["source_id"] and a["source"]["fetched_at"] and a["filed_at"]
            assert a["source"]["raw_path"]
            datetime.fromisoformat(a["filed_at"])
        m = e["materiality"]
        assert m["components"] and m["components"][0]["code"] == "type"
        assert abs(sum(c["points"] for c in m["components"]) - m["raw_total"]) < 1e-9 or any(c["code"] in {"floor", "routine_cap"} for c in m["components"])
        assert e["explanation"]["what"] and e["explanation"]["why"] and e["explanation"]["grounded"]


def test_results_extracted_and_duplicates_collapsed(fixture_run):
    _, _, feed, _ = fixture_run
    [e] = [x for x in by_symbol(feed, "KESTREL", "results") if x["subtype"] == "financial_results"]
    r = e["results"]
    assert r["status"] == "ok" and r["basis"] == "consolidated"
    pat = next(x for x in r["rows"] if x["key"] == "pat")
    assert pat["current"]["value"] == 90.06 and round(pat["yoy"], 4) == round(90.06 / 88.02 - 1, 4)
    dups = [a for a in e["announcements"] if a["duplicate_of"]]
    assert {a["source"]["source"] for a in dups} == {"bse", "nse"}
    assert any(a["supersedes"] for a in e["announcements"])  # corrigendum linked, not dropped


def test_unavailable_attachment_is_reported_not_filled(fixture_run):
    _, _, feed, _ = fixture_run
    [e] = by_symbol(feed, "LOTUS", "results")
    assert e["results"]["status"] == "unavailable" and e["attachment"]["status"] == "unavailable"
    assert "could not be extracted" in e["explanation"]["what"]


def test_source_gaps_are_surfaced(fixture_run):
    _, res, feed, _ = fixture_run
    gaps = {(u["symbol"], u["source"]) for u in feed["unavailable"]}
    assert ("PRAGATI", "bse") in gaps and ("HELIX", "eod") in gaps
    assert any("does not match" in r for r in feed["rejections"])


def test_market_moves_and_explanations(fixture_run):
    _, _, feed, _ = fixture_run
    m = {x["symbol"]: x for x in feed["market"]}
    assert round(m["MERIDIAN"]["signal"]["ret_1d"], 3) == 0.068 and m["MERIDIAN"]["explaining_event_ids"] == []
    assert round(m["SARANG"]["signal"]["vol_ratio_20d"], 1) == 2.6 and m["SARANG"]["explaining_event_ids"]
    anvil = m["ANVIL"]["signal"]
    assert anvil["split_or_bonus_on_date"] is False  # split was earlier, not on the latest session


def test_floor_and_routine_tiers(fixture_run):
    _, _, feed, _ = fixture_run
    [rating] = by_symbol(feed, "SARANG", "credit_rating")
    assert rating["materiality"]["tier"] == "interrupt" and rating["materiality"]["floor"]
    for e in feed["events"]:
        if e["routine"]:
            assert e["materiality"]["tier"] == "routine"


def test_rerun_is_idempotent(fixture_run, tmp_path):
    from finn_engine import fixtures as fx
    from finn_engine.config import ENGINE_DIR, load
    from finn_engine.pipeline import FileInputs, run
    from finn_engine.store import Store
    cfg, res, _, root = fixture_run
    store = Store(root / "t.db")
    again = run(cfg, FileInputs(root / "inputs", fixture=True), store, fx.FIXTURE_FROM, fx.FIXTURE_TO, "fixture", use_llm=False)
    assert sorted(e.id for e in again.events) == sorted(e.id for e in res.events)
    n = store.db.execute("select count(*) from events").fetchone()[0]
    assert n == len(res.events)
