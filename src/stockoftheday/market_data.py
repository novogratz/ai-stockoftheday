"""yfinance-backed market data: daily snapshots + batch prefetch with disk cache."""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
YF_CACHE = DATA_DIR / "yfinance_cache"
SNAPSHOT_CACHE = DATA_DIR / "snapshot_cache.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
YF_CACHE.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(YF_CACHE))

SNAPSHOT_CACHE_TTL = 18 * 60 * 60  # daily bars are stale after 18h


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    last_close: float        # yesterday's completed close
    prev_close: float        # two sessions ago (for yesterday's % change)
    yesterday_high: float
    yesterday_low: float
    avg_volume_20: float     # 20-day average daily volume
    yesterday_volume: float
    atr14: float             # ATR(14) in dollars
    ema5: float
    ema20: float

    @property
    def yesterday_pct_change(self) -> float:
        if self.prev_close == 0:
            return 0.0
        return (self.last_close - self.prev_close) / self.prev_close * 100

    @property
    def rel_volume(self) -> float:
        return self.yesterday_volume / self.avg_volume_20 if self.avg_volume_20 else 0.0

    @property
    def atr_pct(self) -> float:
        return self.atr14 / self.last_close * 100 if self.last_close else 0.0

    @property
    def close_strength(self) -> float:
        """0 = closed at the low, 1 = closed at the high."""
        rng = self.yesterday_high - self.yesterday_low
        return (self.last_close - self.yesterday_low) / rng if rng > 0 else 0.5


def _atr14(df: pd.DataFrame) -> float:
    hi, lo, pc = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(14).mean())


def _ema(series: pd.Series, period: int) -> float:
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def build_snapshot(symbol: str, df: pd.DataFrame) -> Optional[Snapshot]:
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(df) < 22:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    avg_vol = float(df["Volume"].tail(20).mean())
    if avg_vol == 0:
        return None
    return Snapshot(
        symbol=symbol,
        last_close=float(last["Close"]),
        prev_close=float(prev["Close"]),
        yesterday_high=float(last["High"]),
        yesterday_low=float(last["Low"]),
        avg_volume_20=avg_vol,
        yesterday_volume=float(last["Volume"]),
        atr14=_atr14(df),
        ema5=_ema(df["Close"], 5),
        ema20=_ema(df["Close"], 20),
    )


def _extract_ticker_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in raw.columns.get_level_values(0):
            return raw[symbol].copy()
        return pd.DataFrame()
    return raw.copy()


def _snapshot_to_dict(s: Snapshot) -> dict:
    return {
        "symbol": s.symbol,
        "last_close": s.last_close,
        "prev_close": s.prev_close,
        "yesterday_high": s.yesterday_high,
        "yesterday_low": s.yesterday_low,
        "avg_volume_20": s.avg_volume_20,
        "yesterday_volume": s.yesterday_volume,
        "atr14": s.atr14,
        "ema5": s.ema5,
        "ema20": s.ema20,
    }


def _snapshot_from_dict(data: dict) -> Optional[Snapshot]:
    try:
        return Snapshot(
            symbol=data["symbol"],
            last_close=float(data["last_close"]),
            prev_close=float(data["prev_close"]),
            yesterday_high=float(data["yesterday_high"]),
            yesterday_low=float(data["yesterday_low"]),
            avg_volume_20=float(data["avg_volume_20"]),
            yesterday_volume=float(data["yesterday_volume"]),
            atr14=float(data["atr14"]),
            ema5=float(data["ema5"]),
            ema20=float(data["ema20"]),
        )
    except Exception:
        return None


class MarketData:
    """
    Snapshot provider with in-memory + disk cache.

    prefetch(symbols) batch-downloads 1y of daily bars via yf.download —
    much faster than sequential Ticker().history() calls. Raw frames are
    kept in memory because the signal builder needs full OHLCV history.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Optional[Snapshot]] = {}
        self._frames: dict[str, pd.DataFrame] = {}
        self._disk_loaded = False

    def _load_disk_cache(self) -> None:
        if self._disk_loaded:
            return
        self._disk_loaded = True
        if not SNAPSHOT_CACHE.exists():
            return
        try:
            if time.time() - SNAPSHOT_CACHE.stat().st_mtime > SNAPSHOT_CACHE_TTL:
                return
            raw = json.loads(SNAPSHOT_CACHE.read_text(encoding="utf-8"))
            for symbol, payload in raw.items():
                if isinstance(payload, dict):
                    snap = _snapshot_from_dict(payload)
                    if snap is not None:
                        self._cache[symbol] = snap
        except Exception:
            return

    def _persist_cache(self) -> None:
        try:
            data = {sym: _snapshot_to_dict(s) for sym, s in self._cache.items() if s is not None}
            SNAPSHOT_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_frame(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._frames.get(symbol)

    def snapshot(self, symbol: str) -> Optional[Snapshot]:
        self._load_disk_cache()
        if symbol in self._cache:
            return self._cache[symbol]
        result = self._fetch_one(symbol)
        self._cache[symbol] = result
        if result is not None:
            self._persist_cache()
        return result

    def prefetch(self, symbols: list[str], batch_size: int = 200, progress_cb=None) -> None:
        self._load_disk_cache()
        # Frames are memory-only, so anything missing a frame must be re-downloaded
        to_fetch = [s for s in symbols if s not in self._cache or s not in self._frames]
        total = len(to_fetch)
        done = 0

        for i in range(0, total, batch_size):
            batch = to_fetch[i : i + batch_size]
            raw = pd.DataFrame()
            for attempt in range(1, 4):
                try:
                    raw = yf.download(
                        batch,
                        period="1y",
                        interval="1d",
                        auto_adjust=False,
                        progress=False,
                        group_by="ticker",
                        threads=False,
                        timeout=30,
                    )
                    if not raw.empty:
                        break
                except Exception:
                    raw = pd.DataFrame()
                if attempt < 3:
                    time.sleep(1.5 * attempt)

            for sym in batch:
                try:
                    df = _extract_ticker_frame(raw, sym)
                    if df.empty:
                        self._cache.setdefault(sym, None)
                    else:
                        self._frames[sym] = df
                        self._cache[sym] = build_snapshot(sym, df)
                except Exception:
                    self._cache.setdefault(sym, None)

            done += len(batch)
            if progress_cb:
                progress_cb(done, total)

        self._persist_cache()

    def _fetch_one(self, symbol: str) -> Optional[Snapshot]:
        try:
            daily = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=False)
            if daily.empty:
                return None
            self._frames[symbol] = daily
            return build_snapshot(symbol, daily)
        except Exception:
            return None
