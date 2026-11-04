from datetime import date

from finn_engine.models import Classification, Company, Facts, MarketSignal
from finn_engine.materiality import FLOOR_SCORE, ROUTINE_CAP, score


def cls(cat, sub, routine=False):
    return Classification(category=cat, subtype=sub, routine=routine)


def test_components_add_up_and_are_inspectable():
    m = score(Company(symbol="Q", name="Q", revenue_ttm_cr=2150), cls("press_release", "order_win"), Facts(amounts_cr=[410]), None, None, False)
    assert m.raw_total == sum(c.points for c in m.components)
    size = next(c for c in m.components if c.code == "size")
    assert size.points == 25 and size.inputs["ratio"] == round(410 / 2150, 4)
    assert "19.1% of trailing revenue" in size.detail


def test_size_not_assessed_without_reference():
    m = score(Company(symbol="Q", name="Q"), cls("capex", "expansion"), Facts(amounts_cr=[1150]), None, None, False)
    size = next(c for c in m.components if c.code == "size")
    assert size.points == 0 and "not assessed" in size.detail


def test_small_amount_reduces_score():
    m = score(Company(symbol="Q", name="Q", market_cap_cr=100000), cls("mna", "acquisition_or_divestment"), Facts(amounts_cr=[50]), None, None, False)
    assert next(c for c in m.components if c.code == "size").points < 0


def test_hard_floor_for_downgrade():
    m = score(Company(symbol="S", name="S"), cls("credit_rating", "downgrade"), Facts(), None, None, False)
    assert m.score >= FLOOR_SCORE and m.tier == "interrupt" and m.floor


def test_routine_capped_even_with_big_reaction():
    sig = MarketSignal(symbol="X", date=date(2026, 11, 3), close=1, prev_close=1, ret_1d=0.08, avg_vol_20d=1, vol_ratio_20d=5, ret_stdev_60d=0.01, ret_z=8, bars_used=90)
    m = score(Company(symbol="X", name="X"), cls("unclassified", "trading_window", routine=True), Facts(), None, sig, False)
    assert m.score <= ROUTINE_CAP and m.tier == "routine"


def test_reaction_pending_is_stated():
    m = score(Company(symbol="X", name="X"), cls("results", "financial_results"), Facts(), None, None, True)
    r = next(c for c in m.components if c.code == "reaction")
    assert r.points == 0 and "not yet available" in r.detail


def test_split_day_reaction_not_scored():
    sig = MarketSignal(symbol="X", date=date(2026, 10, 15), close=1, prev_close=2, ret_1d=0.001, avg_vol_20d=1, vol_ratio_20d=1, ret_stdev_60d=0.01, ret_z=0.1, bars_used=90, split_or_bonus_on_date=True)
    m = score(Company(symbol="X", name="X"), cls("bonus_split", "split"), Facts(), None, sig, False)
    assert "not scored" in next(c for c in m.components if c.code == "reaction").detail


def test_tiers():
    assert score(Company(symbol="X", name="X"), cls("investor_meetings", "meeting_schedule", True), Facts(), None, None, False).tier == "routine"
    assert score(Company(symbol="X", name="X"), cls("results", "financial_results"), Facts(), None, None, False).tier == "brief"
