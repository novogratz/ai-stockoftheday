import numpy as np
import pandas as pd

from stockoftheday.context import MarketContext
from stockoftheday.market_data import Snapshot
from stockoftheday.strategy import SmartStrategy


class FakeMarketData:
    def __init__(self, snapshots, frames):
        self._snapshots = snapshots
        self._frames = frames

    def snapshot(self, symbol):
        return self._snapshots.get(symbol)

    def get_frame(self, symbol):
        return self._frames.get(symbol)


def _ctx(**kw):
    defaults = dict(
        spy_5d_pct=1.0, sector_returns={}, trending=set(),
        spy_above_sma50=True, spy_above_sma200=True,
        spy_sma50=500.0, spy_sma200=480.0, spy_price=510.0, vix_level=15.0,
    )
    defaults.update(kw)
    return MarketContext(**defaults)


def _snapshot(symbol="MOMO", last_close=105.0, prev_close=100.0, rel_vol=3.0):
    return Snapshot(
        symbol=symbol, last_close=last_close, prev_close=prev_close,
        yesterday_high=last_close * 1.005, yesterday_low=prev_close * 0.99,
        avg_volume_20=1_000_000, yesterday_volume=1_000_000 * rel_vol,
        atr14=last_close * 0.03, ema5=last_close * 0.97, ema20=last_close * 0.94,
    )


def _uptrend_frame(n=260, start=50.0, end=105.0):
    closes = np.linspace(start, end, n)
    return pd.DataFrame({
        "Close": closes,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Volume": np.linspace(800_000, 3_000_000, n),
    })


def test_scan_ranks_strong_momentum_first():
    strong = _snapshot("MOMO", last_close=105.0, prev_close=100.0, rel_vol=3.0)
    weak = _snapshot("MEH", last_close=100.8, prev_close=100.0, rel_vol=1.0)
    md = FakeMarketData(
        {"MOMO": strong, "MEH": weak},
        {"MOMO": _uptrend_frame(), "MEH": _uptrend_frame(end=100.8)},
    )
    strategy = SmartStrategy(market_data=md, ctx=_ctx())
    picks = strategy.scan(["MEH", "MOMO"], enrich=False)
    assert [p.symbol for p in picks][0] == "MOMO"
    assert picks[0].score > picks[1].score


def test_base_filters_reject_below_ema20_and_down_days():
    down = Snapshot(
        symbol="DOWN", last_close=95.0, prev_close=100.0,
        yesterday_high=100.0, yesterday_low=94.0,
        avg_volume_20=1_000_000, yesterday_volume=1_000_000,
        atr14=2.0, ema5=97.0, ema20=98.0,
    )
    md = FakeMarketData({"DOWN": down}, {"DOWN": _uptrend_frame()})
    strategy = SmartStrategy(market_data=md, ctx=_ctx())
    assert strategy.scan(["DOWN"], enrich=False) == []


def test_bear_regime_scores_lower_than_bull():
    snap = _snapshot()
    frame = _uptrend_frame()
    bull = SmartStrategy(
        market_data=FakeMarketData({"MOMO": snap}, {"MOMO": frame}),
        ctx=_ctx(),
    ).scan(["MOMO"], enrich=False)[0]
    bear = SmartStrategy(
        market_data=FakeMarketData({"MOMO": snap}, {"MOMO": frame}),
        ctx=_ctx(spy_above_sma50=False, spy_above_sma200=False, vix_level=32.0),
    ).scan(["MOMO"], enrich=False)[0]
    assert bear.score < bull.score


def test_confidence_tiers():
    snap = _snapshot()
    frame = _uptrend_frame()
    pick = SmartStrategy(
        market_data=FakeMarketData({"MOMO": snap}, {"MOMO": frame}),
        ctx=_ctx(),
    ).scan(["MOMO"], enrich=False)[0]
    assert pick.confidence in {"HIGH", "MEDIUM", "LOW"}
    if pick.score >= 80:
        assert pick.confidence == "HIGH"
