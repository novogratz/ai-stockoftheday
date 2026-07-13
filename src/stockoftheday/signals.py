"""Per-ticker technical signals computed from 1 year of daily OHLCV."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Signals:
    """9 indicators synthesized from IBKR / Minervini / CANSLIM quant research."""
    pct_5d: float         # 5-day price return %
    pct_20d: float        # 20-day price return %
    high_20d: float       # 20-day high (breakout reference)
    vol_trend: float      # 5d avg vol / 20d avg vol (>1 = rising)
    obv_score: float      # volume-weighted up/down, -1 to +1
    rsi14: float          # RSI(14) — 0-100
    macd_diff: float      # MACD line − signal line (>0 = bullish)
    macd_crossed: bool    # MACD crossed above signal in last 3 bars
    sma50: float
    sma150: float         # Minervini Stage 2
    sma200: float         # Minervini Stage 2
    high_52w: float       # CANSLIM "N" — leadership proxy
    vol_1yr_ratio: float  # yesterday_vol / 1yr max vol (>=1.0 = 1yr volume record)
    consec_green: int     # consecutive up-close days (2-3 = sweet spot, 5+ = extended)


def calc_rsi(closes: np.ndarray, period: int = 14) -> float:
    """RSI(period) — returns 50.0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 10):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g = gains[-period:].mean()
    avg_l = losses[-period:].mean()
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return float(100 - 100 / (1 + rs))


def calc_macd(closes: np.ndarray) -> tuple[float, bool]:
    """MACD(12,26,9) → (macd_diff, crossed_bullish_in_last_3_bars)."""
    if len(closes) < 35:
        return 0.0, False
    s = pd.Series(closes)
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    diff_arr = (macd - sig).values
    macd_diff = float(diff_arr[-1])
    crossed = any(
        diff_arr[-(i + 2)] <= 0 and diff_arr[-(i + 1)] > 0
        for i in range(min(3, len(diff_arr) - 1))
    )
    return macd_diff, crossed


def build_signals(df: pd.DataFrame) -> Signals:
    df = df.dropna(subset=["Close", "High", "Volume"])
    n = len(df)
    cls = df["Close"].values.astype(float)
    hig = df["High"].values.astype(float)
    vol = df["Volume"].values.astype(float)

    pct_5d = float((cls[-1] - cls[-6]) / cls[-6] * 100) if n >= 7 else 0.0
    pct_20d = float((cls[-1] - cls[-21]) / cls[-21] * 100) if n >= 22 else 0.0
    high_20d = float(hig[-20:].max()) if n >= 20 else float(cls[-1])

    vol_5d = float(vol[-5:].mean()) if n >= 5 else float(vol.mean())
    vol_20d = float(vol[-20:].mean()) if n >= 20 else float(vol.mean())
    vol_trend = vol_5d / vol_20d if vol_20d > 0 else 1.0

    days = min(10, n - 1)
    vw_sum = vw_tot = 0.0
    for i in range(-days, 0):
        direction = 1 if cls[i] > cls[i - 1] else (-1 if cls[i] < cls[i - 1] else 0)
        vw_sum += direction * vol[i]
        vw_tot += vol[i]
    obv_score = vw_sum / vw_tot if vw_tot > 0 else 0.0

    rsi14 = calc_rsi(cls)
    macd_diff, macd_crossed = calc_macd(cls)

    sma50 = float(cls[-50:].mean()) if n >= 50 else float(cls.mean())
    sma150 = float(cls[-150:].mean()) if n >= 150 else float(cls.mean())
    sma200 = float(cls[-200:].mean()) if n >= 200 else float(cls.mean())

    high_52w = float(hig[-252:].max()) if n >= 60 else float(hig.max())

    vol_252 = float(vol[-252:].max()) if n >= 60 else float(vol.max())
    vol_1yr_ratio = float(vol[-1]) / vol_252 if vol_252 > 0 else 0.0

    consec_green = 0
    for i in range(-1, -min(10, n), -1):
        if cls[i] > cls[i - 1]:
            consec_green += 1
        else:
            break

    return Signals(
        pct_5d=pct_5d, pct_20d=pct_20d, high_20d=high_20d,
        vol_trend=vol_trend, obv_score=obv_score,
        rsi14=rsi14, macd_diff=macd_diff, macd_crossed=macd_crossed,
        sma50=sma50, sma150=sma150, sma200=sma200,
        high_52w=high_52w, vol_1yr_ratio=vol_1yr_ratio,
        consec_green=consec_green,
    )
