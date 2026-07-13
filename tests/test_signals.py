import numpy as np
import pandas as pd

from stockoftheday.signals import build_signals, calc_macd, calc_rsi


def _df(closes, volumes=None):
    closes = np.asarray(closes, dtype=float)
    volumes = np.asarray(volumes if volumes is not None else [1_000_000] * len(closes), dtype=float)
    return pd.DataFrame({
        "Close": closes,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Volume": volumes,
    })


def test_rsi_all_gains_is_100():
    closes = np.arange(1, 40, dtype=float)
    assert calc_rsi(closes) == 100.0


def test_rsi_insufficient_data_returns_neutral():
    assert calc_rsi(np.array([1.0, 2.0, 3.0])) == 50.0


def test_rsi_downtrend_below_uptrend():
    up = calc_rsi(np.linspace(100, 150, 60))
    down = calc_rsi(np.linspace(150, 100, 60))
    assert down < 50 < up


def test_macd_bullish_crossover_detected():
    # Long decline then a sharp 4-bar reversal → cross lands inside the 3-bar window
    closes = np.concatenate([np.linspace(100, 80, 50), np.linspace(80, 95, 4)])
    diff, crossed = calc_macd(closes)
    assert crossed
    assert diff > 0


def test_macd_old_crossover_not_flagged_as_fresh():
    # Same reversal but 10 bars ago — still bullish, no longer a fresh cross
    closes = np.concatenate([np.linspace(100, 80, 50), np.linspace(80, 95, 10)])
    diff, crossed = calc_macd(closes)
    assert not crossed
    assert diff > 0


def test_macd_insufficient_data():
    assert calc_macd(np.arange(10, dtype=float)) == (0.0, False)


def test_build_signals_uptrend():
    closes = np.linspace(50, 100, 260)
    sig = build_signals(_df(closes))
    assert sig.pct_5d > 0
    assert sig.pct_20d > 0
    assert sig.sma50 > sig.sma150 > sig.sma200
    assert sig.consec_green >= 5
    assert sig.high_52w >= closes[-1]


def test_build_signals_consec_green_stops_on_red_day():
    closes = list(np.linspace(50, 100, 60)) + [99.0, 100.0, 101.0]
    sig = build_signals(_df(closes))
    assert sig.consec_green == 2
