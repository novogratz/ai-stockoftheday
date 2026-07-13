from datetime import datetime

from stockoftheday.schedule import MARKET_TZ, is_market_session, is_morning_window


def _dt(hour, minute, weekday_date="2026-07-13"):  # a Monday
    y, m, d = map(int, weekday_date.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=MARKET_TZ)


def test_market_session_bounds():
    assert not is_market_session(_dt(9, 29))
    assert is_market_session(_dt(9, 30))
    assert is_market_session(_dt(16, 0))
    assert not is_market_session(_dt(16, 1))


def test_weekend_never_in_session():
    saturday = _dt(12, 0, "2026-07-18")
    assert not is_market_session(saturday)
    assert not is_morning_window(saturday)


def test_morning_window_before_open():
    assert not is_morning_window(_dt(8, 44))
    assert is_morning_window(_dt(8, 45))
    assert is_morning_window(_dt(9, 29))
    assert not is_morning_window(_dt(9, 30))
