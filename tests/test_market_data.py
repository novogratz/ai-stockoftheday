import numpy as np
import pandas as pd

from stockoftheday.market_data import Snapshot, build_snapshot


def _ohlcv(closes):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Open": closes * 0.995,
        "High": closes * 1.01,
        "Low": closes * 0.98,
        "Close": closes,
        "Volume": [1_000_000] * len(closes),
    })


def test_build_snapshot_requires_22_bars():
    assert build_snapshot("X", _ohlcv(range(1, 10))) is None
    assert build_snapshot("X", _ohlcv(np.linspace(10, 20, 30))) is not None


def test_snapshot_derived_properties():
    snap = Snapshot(
        symbol="X", last_close=102.0, prev_close=100.0,
        yesterday_high=103.0, yesterday_low=99.0,
        avg_volume_20=1_000_000, yesterday_volume=2_500_000,
        atr14=2.04, ema5=101.0, ema20=98.0,
    )
    assert abs(snap.yesterday_pct_change - 2.0) < 1e-9
    assert abs(snap.rel_volume - 2.5) < 1e-9
    assert abs(snap.atr_pct - 2.0) < 1e-9
    assert abs(snap.close_strength - 0.75) < 1e-9  # closed in the upper quarter


def test_close_strength_defaults_to_half_on_zero_range():
    snap = Snapshot(
        symbol="X", last_close=100.0, prev_close=100.0,
        yesterday_high=100.0, yesterday_low=100.0,
        avg_volume_20=1.0, yesterday_volume=1.0,
        atr14=1.0, ema5=100.0, ema20=100.0,
    )
    assert snap.close_strength == 0.5
