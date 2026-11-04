from datetime import date, datetime, timedelta, timezone

import pytest

from finn_engine.market import explaining_window, reaction_session, signal_at
from finn_engine.models import EodBar

IST = timezone(timedelta(hours=5, minutes=30))


def bars(n=80, last_ret=0.0, last_vol_mult=1.0, split_at: int | None = None):
    out = []
    d = date(2026, 6, 1)
    px = 100.0
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        px *= 1 + (0.01 if i % 2 else -0.01)
        out.append(EodBar(date=d, open=px, high=px, low=px, close=px, adj_close=px, volume=1000))
        d += timedelta(days=1)
    out[-1] = out[-1].model_copy(update={"adj_close": out[-2].adj_close * (1 + last_ret), "close": out[-2].close * (1 + last_ret), "volume": int(1000 * last_vol_mult)})
    if split_at is not None:
        for i in range(split_at):
            out[i] = out[i].model_copy(update={"close": out[i].close * 2})  # raw pre-split prices doubled
    return out


def test_return_uses_adjusted_close_and_volume_excludes_today():
    s = signal_at("X", bars(last_ret=0.05, last_vol_mult=3.0), set())
    assert s.ret_1d == pytest.approx(0.05)
    assert s.avg_vol_20d == 1000 and s.vol_ratio_20d == pytest.approx(3.0)


def test_z_score_against_own_volatility():
    s = signal_at("X", bars(last_ret=0.05), set())
    assert s.ret_stdev_60d == pytest.approx(0.01, rel=0.05)
    assert s.ret_z == pytest.approx(5.0, rel=0.05)


def test_split_day_is_flagged_and_adjusted_return_is_normal():
    b = bars(split_at=70)
    s = signal_at("X", b, {b[70].date}, on=b[70].date)
    assert s.split_or_bonus_on_date is True
    assert abs(s.ret_1d) < 0.02  # raw close halves, adjusted does not
    assert b[70].close / b[69].close - 1 == pytest.approx(-0.5, abs=0.02)


def test_insufficient_history_reports_instead_of_guessing():
    s = signal_at("X", bars(n=10), set())
    assert s.vol_ratio_20d is None and s.ret_z is None and "15 prior sessions" in s.note


def test_reaction_session_after_hours_rolls_to_next_session():
    b = bars(n=40)
    d = b[20].date
    assert reaction_session(datetime.combine(d, datetime.min.time(), IST).replace(hour=14), b) == d
    assert reaction_session(datetime.combine(d, datetime.min.time(), IST).replace(hour=19), b) == b[21].date
    assert reaction_session(datetime.combine(b[-1].date, datetime.min.time(), IST).replace(hour=19), b) is None


def test_explaining_window_runs_from_previous_close():
    b = bars(n=40)
    lo, hi = explaining_window(b[10].date, b)
    assert lo.date() == b[9].date and hi.date() == b[10].date and lo.hour == 15 and hi.minute == 30
