"""Market-wide context: SPY trend regime, sector returns, VIX, trending tickers, futures bias."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd
import yfinance as yf

from .market_data import DATA_DIR, _extract_ticker_frame
from .universe import SECTOR_ETFS

CONTEXT_CACHE = DATA_DIR / "market_context_cache.json"
FUTURES_CACHE = DATA_DIR / "futures_bias_cache.json"


@dataclass
class MarketContext:
    """SPY + sector + VIX context fetched once per scan — drives the regime gate."""
    spy_5d_pct: float
    sector_returns: dict = field(default_factory=dict)  # ETF symbol → 5d return %
    trending: set = field(default_factory=set)          # Yahoo Finance trending US symbols
    spy_above_sma50: bool = True
    spy_above_sma200: bool = True
    spy_sma50: float = 0.0
    spy_sma200: float = 0.0
    spy_price: float = 0.0
    vix_level: float = 0.0

    @property
    def regime_multiplier(self) -> float:
        """Combined SPY trend (Minervini) + VIX volatility regime multiplier."""
        if self.spy_above_sma50 and self.spy_above_sma200:
            spy_mult = 1.0
        elif self.spy_above_sma200:
            spy_mult = 0.85
        else:
            spy_mult = 0.70

        vix = self.vix_level
        if vix >= 30:
            vix_mult = 0.55   # panic/crisis — extremely selective
        elif vix >= 25:
            vix_mult = 0.70   # elevated fear
        elif vix >= 20:
            vix_mult = 0.88   # mild anxiety
        elif 0 < vix <= 14:
            vix_mult = 1.12   # complacency — momentum runs clean
        else:
            vix_mult = 1.0    # normal (VIX 14-20)

        return spy_mult * vix_mult

    @property
    def regime_label(self) -> str:
        trend = "SPY > SMA50/200" if (self.spy_above_sma50 and self.spy_above_sma200) else (
            "SPY > SMA200 only" if self.spy_above_sma200 else "SPY below SMA200 ⚠️"
        )
        return f"{trend} · VIX {self.vix_level:.1f} · multiplier x{self.regime_multiplier:.2f}"

    @classmethod
    def load_or_fetch(cls, max_age: int = 7_200) -> "MarketContext":
        if CONTEXT_CACHE.exists():
            try:
                if time.time() - CONTEXT_CACHE.stat().st_mtime < max_age:
                    raw = json.loads(CONTEXT_CACHE.read_text(encoding="utf-8"))
                    return cls(
                        spy_5d_pct=float(raw["spy_5d_pct"]),
                        sector_returns={k: float(v) for k, v in raw["sector_returns"].items()},
                        trending=set(raw.get("trending", [])),
                        spy_above_sma50=bool(raw.get("spy_above_sma50", True)),
                        spy_above_sma200=bool(raw.get("spy_above_sma200", True)),
                        spy_sma50=float(raw.get("spy_sma50", 0)),
                        spy_sma200=float(raw.get("spy_sma200", 0)),
                        spy_price=float(raw.get("spy_price", 0)),
                        vix_level=float(raw.get("vix_level", 0.0)),
                    )
            except Exception:
                pass
        return cls._fetch()

    @classmethod
    def _fetch(cls) -> "MarketContext":
        spy_pct = 0.0
        sectors: dict = {}
        trending: set = set()
        spy_above_sma50 = spy_above_sma200 = True
        spy_sma50 = spy_sma200 = spy_price = 0.0
        vix_level = 0.0

        syms = ["SPY"] + SECTOR_ETFS
        try:
            raw = yf.download(
                syms, period="1y", interval="1d",
                auto_adjust=False, progress=False,
                group_by="ticker", threads=False, timeout=20,
            )
            for sym in syms:
                try:
                    df = _extract_ticker_frame(raw, sym).dropna(subset=["Close"])
                    if len(df) < 6:
                        continue
                    c = df["Close"].values.astype(float)
                    pct = float((c[-1] - c[-6]) / c[-6] * 100)
                    if sym == "SPY":
                        spy_pct = pct
                        spy_price = float(c[-1])
                        spy_sma50 = float(c[-50:].mean()) if len(c) >= 50 else spy_price
                        spy_sma200 = float(c[-200:].mean()) if len(c) >= 200 else spy_price
                        spy_above_sma50 = spy_price > spy_sma50
                        spy_above_sma200 = spy_price > spy_sma200
                    else:
                        sectors[sym] = pct
                except Exception:
                    pass
        except Exception:
            pass

        try:
            vix_raw = yf.download("^VIX", period="5d", interval="1d",
                                  auto_adjust=False, progress=False, timeout=10)
            if not vix_raw.empty:
                vix_close = vix_raw["Close"] if "Close" in vix_raw.columns else vix_raw.iloc[:, 0]
                vix_level = float(vix_close.dropna().iloc[-1])
        except Exception:
            pass

        try:
            trending = _fetch_yahoo_trending()
        except Exception:
            pass

        ctx = cls(
            spy_5d_pct=spy_pct, sector_returns=sectors, trending=trending,
            spy_above_sma50=spy_above_sma50, spy_above_sma200=spy_above_sma200,
            spy_sma50=spy_sma50, spy_sma200=spy_sma200, spy_price=spy_price,
            vix_level=vix_level,
        )
        try:
            CONTEXT_CACHE.write_text(json.dumps({
                "spy_5d_pct": spy_pct,
                "sector_returns": sectors,
                "trending": list(trending),
                "spy_above_sma50": spy_above_sma50,
                "spy_above_sma200": spy_above_sma200,
                "spy_sma50": spy_sma50,
                "spy_sma200": spy_sma200,
                "spy_price": spy_price,
                "vix_level": vix_level,
            }, indent=2), encoding="utf-8")
        except Exception:
            pass
        return ctx


def _fetch_yahoo_trending() -> set:
    """Best-effort fetch of trending US tickers from Yahoo Finance screeners."""
    trending: set = set()
    urls = [
        ("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
         "?formatted=true&lang=en-US&region=US&scrIds=day_gainers&count=25"),
        ("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
         "?formatted=true&lang=en-US&region=US&scrIds=most_actives&count=25"),
    ]
    hdrs = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                for q in (data.get("finance", {}).get("result", [{}])[0].get("quotes", [])):
                    sym = str(q.get("symbol", ""))
                    if sym and "." not in sym:
                        trending.add(sym)
        except Exception:
            pass
    return trending


# ──────────────────────────────────────────────────────────────────────────────
# US futures bias — sets the tone for the morning game plan
# ──────────────────────────────────────────────────────────────────────────────

class FuturesBias(Enum):
    GREEN = "green"
    RED = "red"
    NEUTRAL = "neutral"


def get_futures_bias() -> tuple[FuturesBias, str]:
    """
    Checks ES=F (S&P 500 futures) vs 24h ago.
    >= +0.3% → GREEN (buy at open) | <= -0.3% → RED (wait for a bounce) | else NEUTRAL
    """
    try:
        data = yf.Ticker("ES=F").history(period="5d", interval="1h")
        data = data.dropna(subset=["Close"])
        if len(data) < 2:
            return FuturesBias.NEUTRAL, "ES=F: insufficient data"

        last = float(data["Close"].iloc[-1])
        ref = float(data["Close"].iloc[-24] if len(data) >= 24 else data["Close"].iloc[0])
        if ref == 0:
            return FuturesBias.NEUTRAL, "ES=F: invalid reference"

        pct = (last - ref) / ref * 100
        detail = f"ES=F {last:,.0f} pts ({pct:+.2f}% vs 24h ago)"

        if pct >= 0.3:
            bias = FuturesBias.GREEN
        elif pct <= -0.3:
            bias = FuturesBias.RED
        else:
            bias = FuturesBias.NEUTRAL
        _save_cached_futures_bias(bias, detail)
        return bias, detail
    except Exception as exc:
        cached = _load_cached_futures_bias()
        if cached is not None:
            return cached
        return FuturesBias.NEUTRAL, f"ES=F: error - {exc}"


def _load_cached_futures_bias() -> tuple[FuturesBias, str] | None:
    if not FUTURES_CACHE.exists():
        return None
    try:
        if time.time() - FUTURES_CACHE.stat().st_mtime > 18 * 3600:
            return None
        raw = json.loads(FUTURES_CACHE.read_text(encoding="utf-8"))
        bias = FuturesBias(raw.get("bias", "neutral"))
        detail = str(raw.get("detail", "")) or "cached futures bias"
        return bias, detail + " (cached)"
    except Exception:
        return None


def _save_cached_futures_bias(bias: FuturesBias, detail: str) -> None:
    try:
        FUTURES_CACHE.write_text(
            json.dumps({"bias": bias.value, "detail": detail, "updated": time.time()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
