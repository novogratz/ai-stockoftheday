from datetime import datetime

import pytest

import stockoftheday.portfolio as portfolio
from stockoftheday.schedule import MARKET_TZ
from stockoftheday.strategy import Pick


@pytest.fixture(autouse=True)
def _tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "PORTFOLIO_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "LEDGER_FILE", tmp_path / "ledger.json")


def _pick(symbol="NVDA", last_close=100.0, gap_pct=2.0, score=90.0):
    return Pick(
        symbol=symbol, last_close=last_close, score=score, yesterday_pct=3.0,
        rel_volume=2.0, atr_pct=3.0, close_strength=0.8,
        above_ema5=True, above_ema20=True, gap_pct=gap_pct,
    )


def _at(day, hour, minute=0):
    y, m, d = map(int, day.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=MARKET_TZ)


MON = "2026-07-13"
TUE = "2026-07-14"


def test_record_dedupes_per_day_and_marks_first_as_portfolio_pick():
    when = _at(MON, 10)
    assert portfolio.record_picks([_pick("AAA"), _pick("BBB")], when=when) == 2
    assert portfolio.record_picks([_pick("AAA"), _pick("CCC")], when=when) == 1  # AAA dup

    ledger = portfolio.load_ledger()
    rows = {p["symbol"]: p for p in ledger["picks"]}
    assert set(rows) == {"AAA", "BBB", "CCC"}
    assert rows["AAA"]["is_portfolio_pick"] is True
    assert rows["BBB"]["is_portfolio_pick"] is False
    # buy price = last_close adjusted by live gap
    assert rows["AAA"]["buy_price"] == pytest.approx(102.0)


def test_same_symbol_allowed_on_a_different_day():
    portfolio.record_picks([_pick("AAA")], when=_at(MON, 10))
    assert portfolio.record_picks([_pick("AAA")], when=_at(TUE, 10)) == 1
    ledger = portfolio.load_ledger()
    assert len(ledger["picks"]) == 2
    # each day gets its own portfolio pick
    assert all(p["is_portfolio_pick"] for p in ledger["picks"])


def test_settle_skips_today_before_close_and_settles_after():
    portfolio.record_picks([_pick("AAA")], when=_at(MON, 10))
    fetch = lambda sym, day: 105.0

    assert portfolio.settle(when=_at(MON, 15), fetch_close=fetch) == 0  # market still open
    assert portfolio.settle(when=_at(MON, 16, 30), fetch_close=fetch) == 1

    row = portfolio.load_ledger()["picks"][0]
    assert row["close_price"] == 105.0
    assert row["day_return_pct"] == pytest.approx(2.941, abs=0.001)  # 102 → 105


def test_portfolio_balance_compounds_only_on_portfolio_picks():
    portfolio.record_picks([_pick("AAA"), _pick("BBB")], when=_at(MON, 10))
    portfolio.record_picks([_pick("CCC")], when=_at(TUE, 10))

    closes = {"AAA": 112.2, "BBB": 51.0, "CCC": 96.9}  # +10%, whatever, -5%
    fetch = lambda sym, day: closes[sym]
    portfolio.settle(when=_at(TUE, 17), fetch_close=fetch)

    ledger = portfolio.load_ledger()
    # 10_000 * 1.10 (AAA, Mon) * 0.95 (CCC, Tue) — BBB tracked but not traded
    assert ledger["balance"] == pytest.approx(10_450.0, abs=0.5)

    s = portfolio.stats(ledger)
    assert s["picks_settled"] == 3
    assert s["portfolio_days"] == 2
    assert s["win_rate"] == pytest.approx(100 / 3, abs=0.1)


def test_unpriceable_rows_stay_unsettled_for_retry():
    portfolio.record_picks([_pick("AAA")], when=_at(MON, 10))
    assert portfolio.settle(when=_at(MON, 17), fetch_close=lambda s, d: None) == 0
    assert portfolio.load_ledger()["picks"][0]["close_price"] is None
    assert portfolio.load_ledger()["balance"] == 10_000.0


def test_status_lines_show_live_position_and_alltime():
    portfolio.record_picks([_pick("AAA")], when=_at(MON, 10))
    lines = portfolio.status_lines(when=_at(MON, 12), live_fetch=lambda s: 107.1)
    joined = "\n".join(lines)
    assert "AAA" in joined and "+5.00%" in joined          # 102 → 107.1
    assert "$10,500.00" in joined and "+5.00% since start" in joined


def test_eod_report_lists_picks_and_standing():
    portfolio.record_picks([_pick("AAA"), _pick("BBB", last_close=50.0, gap_pct=0.0)],
                           when=_at(MON, 10))
    portfolio.settle(when=_at(MON, 17),
                     fetch_close=lambda s, d: {"AAA": 104.04, "BBB": 49.0}[s])
    text = portfolio.build_eod_report(when=_at(MON, 17))
    assert "End of Day" in text
    assert "AAA ⭐" in text and "+2.00%" in text
    assert "🔴 BBB" in text
    assert "Paper portfolio: $10,200.00" in text