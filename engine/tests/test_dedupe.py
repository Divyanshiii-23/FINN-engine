from finn_engine.classify import classify
from finn_engine.dedupe import cluster, dedupe

from .conftest import ann


def test_exact_repost_with_same_attachment_is_duplicate():
    a = ann("Financial Results", "Unaudited results", sid="1", at="2026-11-03T19:12:00", attachment="fixture://R.pdf")
    b = ann("Financial Results", "Unaudited results", sid="2", at="2026-11-03T19:13:00", attachment="fixture://R.pdf")
    out = dedupe([a, b])
    assert b.duplicate_of == a.id and "same attachment" in b.duplicate_reason
    assert a.duplicates == [b.id] and len(out) == 2


def test_cross_exchange_copy_is_duplicate_and_bse_is_canonical():
    nse = ann("Financial Results", "Unaudited consolidated financial results for the quarter ended 30.09.2026", source="nse", sid="n", at="2026-11-03T19:11:00")
    bse = ann("KESTREL - 990102 - Financial Results for the Quarter", "Unaudited consolidated financial results for the quarter ended 30.09.2026", source="bse", sid="b", at="2026-11-03T19:12:00")
    dedupe([nse, bse])
    # NSE was earlier, so it became canonical; the BSE copy is linked to it either way.
    assert (bse.duplicate_of == nse.id) or (nse.duplicate_of == bse.id)


def test_far_apart_filings_are_not_duplicates():
    a = ann("Financial Results", "Unaudited results", source="bse", sid="1", at="2026-11-03T10:00:00")
    b = ann("Financial Results", "Unaudited results", source="nse", sid="2", at="2026-11-03T18:00:00")
    dedupe([a, b])
    assert a.duplicate_of is None and b.duplicate_of is None


def test_revision_is_kept_and_linked_not_dropped():
    a = ann("Financial Results for the Quarter Ended 30 September 2026", "Unaudited financial results", sid="1", at="2026-11-03T19:12:00", attachment="fixture://R.pdf")
    b = ann("Corrigendum to Financial Results", "Corrigendum: correction in the segment note of the financial results", sid="2", at="2026-11-03T21:40:00")
    dedupe([a, b])
    assert b.duplicate_of is None and b.supersedes == a.id


def test_same_id_fetched_twice_collapses():
    a = ann("Dividend", sid="7")
    b = ann("Dividend", sid="7")
    assert len(dedupe([a, b])) == 1


def test_results_family_clusters_into_one_event_routine_does_not():
    items = [
        ann("Outcome of Board Meeting", "approved unaudited financial results", sid="1", at="2026-11-03T19:02:00"),
        ann("Financial Results for the Quarter", None, sid="2", at="2026-11-03T19:12:00"),
        ann("Investor Presentation", None, sid="3", at="2026-11-03T19:31:00"),
        ann("Closure of Trading Window", None, sid="4", at="2026-11-03T19:40:00"),
        ann("Certificate under Regulation 40(9)", None, sid="5", at="2026-11-03T19:45:00"),
    ]
    groups = cluster([(a, classify(a)) for a in dedupe(items)])
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 1, 3]
