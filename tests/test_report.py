from stockoftheday.context import FuturesBias, MarketContext
from stockoftheday.report import build_intraday_report, build_morning_report
from stockoftheday.strategy import Pick


def _ctx():
    return MarketContext(spy_5d_pct=1.0, vix_level=15.0)


def _pick(symbol="NVDA", score=92.0):
    return Pick(
        symbol=symbol, last_close=128.45, score=score, yesterday_pct=3.2,
        rel_volume=2.4, atr_pct=3.1, close_strength=0.8,
        above_ema5=True, above_ema20=True, gap_pct=1.2,
    )


def test_morning_report_contains_picks_and_plan():
    text = build_morning_report([_pick()], _ctx(), FuturesBias.GREEN, "ES=F +0.42%", top=3)
    assert "Morning Game Plan" in text
    assert "NVDA" in text
    assert "target" in text and "stop" in text
    assert "09:30" in text and "15:55" in text


def test_morning_report_handles_no_picks():
    text = build_morning_report([], _ctx(), FuturesBias.RED, "ES=F -0.80%")
    assert "No setups" in text


def test_intraday_report_respects_top_limit():
    picks = [_pick(f"SYM{i}", score=90 - i) for i in range(5)]
    text = build_intraday_report(picks, _ctx(), top=3)
    assert "SYM0" in text and "SYM2" in text
    assert "SYM3" not in text


def test_reports_use_telegram_html():
    text = build_morning_report([_pick()], _ctx(), FuturesBias.NEUTRAL, "ES=F flat")
    assert "<b>" in text and "</b>" in text
