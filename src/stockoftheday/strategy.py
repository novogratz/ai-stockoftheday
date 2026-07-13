"""14-signal composite momentum screener (analysis only — no order execution)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import yfinance as yf

from .context import MarketContext
from .market_data import DATA_DIR, MarketData, Snapshot
from .signals import Signals, build_signals
from .universe import SECTOR_MAP

EARNINGS_CACHE = DATA_DIR / "earnings_cache.json"
SHORT_CACHE = DATA_DIR / "short_interest_cache.json"


@dataclass(frozen=True)
class Pick:
    symbol: str
    last_close: float
    score: float
    yesterday_pct: float
    rel_volume: float
    atr_pct: float
    close_strength: float   # 0-1, where 1 = closed at the day high
    above_ema5: bool
    above_ema20: bool
    gap_pct: float = 0.0    # live pre-market/intraday gap from previous close

    @property
    def confidence(self) -> str:
        if self.score >= 80:
            return "HIGH"
        elif self.score >= 45:
            return "MEDIUM"
        return "LOW"

    @property
    def confidence_emoji(self) -> str:
        return {"HIGH": "🔥", "MEDIUM": "✅", "LOW": "⚠️"}[self.confidence]


class SmartStrategy:
    """
    Primary screener — 14-signal composite score (0-~140 pts).

    Signals (synthesized from IBKR, Minervini, CANSLIM, LangChain quant repos):
      A. Momentum alignment  — 1d/5d/20d alignment                    (0-25 pts)
      B. MACD(12,26,9)       — bullish crossover / above signal       (0-12 pts)
      C. RSI(14) zone        — 45-70 = momentum, <35 = bounce         (0-10 pts)
      D. Stage 2 MA align    — Price>SMA50>SMA150>SMA200 [Minervini]  (0-12 pts)
      E. Volume conviction   — rel vol + trend + 1yr breakthrough     (0-18 pts)
      F. 52-week proximity   — within 20% of 52-week high [CANSLIM]   (0-10 pts)
      G. Rel strength SPY    — outperforms SPY 5d return              (0-8 pts)
      H. OBV smart money     — volume-weighted up/down                (0-5 pts)
      I. Bonuses             — close quality + ATR + trending         (0-10 pts)
      J. Sector alignment    — stock in top-performing sector         (0-5 pts)
      K. Earnings blackout   — hard filter: skip if earnings ≤3 days  (filter)
      L. Short squeeze       — float-adjusted short interest bonus    (0-16 pts)
      M. Live gap            — pre-market/intraday gap vs yesterday   (-18 to +20 pts)
      N. Consecutive days    — 2-3 green = sweet spot, 5+ = penalty   (-8 to +6 pts)

    Regime gate: SPY×VIX combined multiplier (0.55-1.12)
    Hard filters: price $1-$1000 | avg vol ≥100k | yesterday ≥+0.5% | above EMA20
    Confidence: HIGH ≥80 | MEDIUM ≥45 | LOW <45
    """

    MIN_PRICE = 1.00
    MAX_PRICE = 1000.00
    MIN_AVG_VOL = 100_000
    MIN_YDAY_VOL = 50_000
    MIN_PCT_CHG = 0.5
    SCAN_LIMIT = 200

    def __init__(
        self,
        market_data: Optional[MarketData] = None,
        ctx: Optional[MarketContext] = None,
    ) -> None:
        self.md = market_data or MarketData()
        self.ctx = ctx or MarketContext.load_or_fetch()

    def scan(self, watchlist: list[str], enrich: bool = True) -> list[Pick]:
        scored: list = []
        for sym in watchlist:
            snap = self.md.snapshot(sym)
            if snap is None or not self._base_ok(snap):
                continue
            df = self.md.get_frame(sym)
            if df is None or len(df) < 7:
                continue
            sig = build_signals(df)
            score = self._score(snap, sig)
            if score > 0:
                scored.append((score, snap, sig))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not enrich:
            return [self._to_pick(score, snap, 0.0) for score, snap, _ in scored[: self.SCAN_LIMIT]]

        # Earnings blackout + float-adjusted squeeze bonus (top 50 only — HTTP-heavy)
        enriched: list = []
        for score, snap, sig in scored[:50]:
            if _is_earnings_blackout(snap.symbol):
                continue
            score += _squeeze_bonus(snap.symbol, snap.yesterday_pct_change)
            enriched.append((score, snap, sig))
        combined = sorted(enriched + scored[50:], key=lambda x: x[0], reverse=True)

        # Live/pre-market gap enrichment — parallel 5m prepost history fetches
        gaps = _fetch_gaps([(snap.symbol, snap.last_close) for _, snap, _ in combined])

        gap_adjusted: list = []
        for score, snap, _sig in combined:
            gap_pct = gaps.get(snap.symbol)
            if gap_pct is not None:
                if gap_pct >= 5.0:
                    score += 20.0   # explosive intraday momentum
                elif gap_pct >= 3.0:
                    score += 14.0
                elif gap_pct >= 1.5:
                    score += 9.0
                elif gap_pct >= 0.5:
                    score += 5.0
                elif gap_pct <= -1.0:
                    score = max(0.0, score - 18.0)  # momentum reversed
                elif gap_pct <= -0.5:
                    score = max(0.0, score - 10.0)
            gap_adjusted.append((score, snap, gap_pct or 0.0))

        gap_adjusted.sort(key=lambda x: x[0], reverse=True)
        return [self._to_pick(score, snap, gap) for score, snap, gap in gap_adjusted[: self.SCAN_LIMIT]]

    def _to_pick(self, score: float, snap: Snapshot, gap_pct: float) -> Pick:
        return Pick(
            symbol=snap.symbol,
            last_close=snap.last_close,
            score=round(score, 2),
            yesterday_pct=snap.yesterday_pct_change,
            rel_volume=snap.rel_volume,
            atr_pct=snap.atr_pct,
            close_strength=snap.close_strength,
            above_ema5=snap.last_close > snap.ema5,
            above_ema20=True,
            gap_pct=round(gap_pct, 2),
        )

    def _base_ok(self, snap: Snapshot) -> bool:
        return (
            self.MIN_PRICE <= snap.last_close <= self.MAX_PRICE
            and snap.avg_volume_20 >= self.MIN_AVG_VOL
            and snap.yesterday_volume >= self.MIN_YDAY_VOL
            and snap.yesterday_pct_change >= self.MIN_PCT_CHG
            and snap.last_close > snap.ema20
        )

    def _score(self, snap: Snapshot, sig: Signals) -> float:
        s = 0.0
        price = snap.last_close

        # A — Momentum cascade (0-25)
        s += min(12.0, snap.yesterday_pct_change * 1.2)
        if sig.pct_5d > 0:
            s += 7.0
        if sig.pct_20d > 0:
            s += 6.0

        # B — MACD(12,26,9) (0-12)
        if sig.macd_crossed:
            s += 12.0
        elif sig.macd_diff > 0:
            s += 6.0

        # C — RSI(14) zone (0-10)
        rsi = sig.rsi14
        if 45 <= rsi <= 70:
            s += 10.0    # momentum zone, not overbought
        elif 35 <= rsi < 45:
            s += 5.0
        elif 30 <= rsi < 35:
            s += 3.0     # oversold bounce candidate

        # D — Minervini Stage 2 MA alignment (0-12)
        if sig.sma50 > 0 and sig.sma150 > 0 and sig.sma200 > 0:
            if price > sig.sma50 > sig.sma150 > sig.sma200:
                s += 12.0
            elif price > sig.sma50 > sig.sma200:
                s += 7.0
            elif price > sig.sma50:
                s += 3.0

        # E — Volume conviction (0-18)
        s += min(8.0, snap.rel_volume * 2.0)
        s += min(5.0, max(0.0, (sig.vol_trend - 1.0) * 5.0))
        if sig.vol_1yr_ratio >= 1.0:
            s += 5.0     # 1-year volume record

        # F — 52-week high proximity / CANSLIM "N" (0-10)
        if sig.high_52w > 0 and price > 0:
            pct_from_high = (sig.high_52w - price) / sig.high_52w
            if pct_from_high <= 0.02:
                s += 10.0
            elif pct_from_high <= 0.10:
                s += 7.0
            elif pct_from_high <= 0.20:
                s += 4.0
            elif pct_from_high <= 0.30:
                s += 1.0

        # G — Relative strength vs SPY (0-8)
        rs = sig.pct_5d - self.ctx.spy_5d_pct
        if rs > 5:
            s += 8.0
        elif rs > 2:
            s += 5.0
        elif rs > 0:
            s += 3.0

        # H — OBV smart money (0-5)
        s += max(0.0, sig.obv_score * 5.0)

        # I — Bonuses: close quality + ATR + trending (0-10)
        s += snap.close_strength * 3.5
        s += min(2.5, snap.atr_pct * 0.5)
        if snap.symbol in self.ctx.trending:
            s += 4.0

        # J — Sector alignment (0-5)
        sector = SECTOR_MAP.get(snap.symbol)
        if sector:
            sector_ret = self.ctx.sector_returns.get(sector, 0.0)
            if sector_ret >= 4.0:
                s += 5.0
            elif sector_ret >= 2.0:
                s += 3.0
            elif sector_ret >= 0.0:
                s += 1.0

        # N — Consecutive green days: sweet spot 2-3, penalise 5+ (extended)
        cg = sig.consec_green
        if cg == 2:
            s += 4.0
        elif cg == 3:
            s += 6.0
        elif cg == 4:
            s -= 3.0
        elif cg >= 5:
            s -= 8.0

        # Market regime gate: never fight the tape
        s *= self.ctx.regime_multiplier

        return s


# ──────────────────────────────────────────────────────────────────────────────
# Live gap fetch — pre-market / intraday move vs yesterday's close
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_gaps(symbols_with_close: list[tuple[str, float]]) -> dict[str, float]:
    def _one(sym: str, lc: float) -> tuple[str, float | None]:
        try:
            df = yf.Ticker(sym).history(period="1d", interval="5m", prepost=True)
            if df.empty:
                return sym, None
            live = float(df["Close"].iloc[-1])
            if live > 0 and lc > 0:
                return sym, (live - lc) / lc * 100
        except Exception:
            pass
        return sym, None

    gaps: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_one, sym, lc) for sym, lc in symbols_with_close]
        for f in as_completed(futures):
            try:
                sym, gap = f.result()
                if gap is not None:
                    gaps[sym] = gap
            except Exception:
                pass
    return gaps


# ──────────────────────────────────────────────────────────────────────────────
# Earnings blackout — skip stocks reporting within the next 3 days
# ──────────────────────────────────────────────────────────────────────────────

_earnings_mem: dict = {}
_earnings_mem_loaded = False


def _load_earnings_mem() -> None:
    global _earnings_mem, _earnings_mem_loaded
    if _earnings_mem_loaded:
        return
    _earnings_mem_loaded = True
    if EARNINGS_CACHE.exists():
        try:
            if time.time() - EARNINGS_CACHE.stat().st_mtime < 12 * 3600:
                _earnings_mem = json.loads(EARNINGS_CACHE.read_text())
        except Exception:
            pass


def _save_earnings_mem() -> None:
    try:
        EARNINGS_CACHE.write_text(json.dumps(_earnings_mem, indent=2))
    except Exception:
        pass


def _is_earnings_blackout(symbol: str, window_days: int = 3) -> bool:
    from datetime import date as _date

    _load_earnings_mem()
    entry = _earnings_mem.get(symbol, {})
    if entry and time.time() - entry.get("ts", 0) < 12 * 3600:
        raw = entry.get("next_earnings")
        if not raw:
            return False
        try:
            delta = (_date.fromisoformat(raw) - _date.today()).days
            return 0 <= delta <= window_days
        except Exception:
            return False

    next_earnings = None
    try:
        dates_df = yf.Ticker(symbol).get_earnings_dates(limit=4)
        if dates_df is not None and not dates_df.empty:
            today = _date.today()
            for dt_idx in sorted(dates_df.index):
                try:
                    d = dt_idx.date()
                    if d >= today:
                        next_earnings = d.isoformat()
                        break
                except Exception:
                    continue
    except Exception:
        pass

    _earnings_mem[symbol] = {"next_earnings": next_earnings, "ts": time.time()}
    _save_earnings_mem()
    if not next_earnings:
        return False
    try:
        delta = (_date.fromisoformat(next_earnings) - _date.today()).days
        return 0 <= delta <= window_days
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Short squeeze radar — short % of float + momentum = squeeze setup
# ──────────────────────────────────────────────────────────────────────────────

_short_mem: dict = {}
_short_mem_loaded = False


def _load_short_mem() -> None:
    global _short_mem, _short_mem_loaded
    if _short_mem_loaded:
        return
    _short_mem_loaded = True
    if SHORT_CACHE.exists():
        try:
            if time.time() - SHORT_CACHE.stat().st_mtime < 24 * 3600:
                _short_mem = json.loads(SHORT_CACHE.read_text())
        except Exception:
            pass


def _save_short_mem() -> None:
    try:
        SHORT_CACHE.write_text(json.dumps(_short_mem, indent=2))
    except Exception:
        pass


def _get_float_info(symbol: str) -> tuple[float, float]:
    """Return (short_pct 0.0-1.0, float_shares). Cached 24h."""
    _load_short_mem()
    entry = _short_mem.get(symbol, {})
    if entry and time.time() - entry.get("ts", 0) < 24 * 3600:
        return float(entry.get("short_pct", 0.0)), float(entry.get("float_shares", 0.0))

    short_pct = 0.0
    float_shares = 0.0
    try:
        info = yf.Ticker(symbol).get_info()
        val = info.get("shortPercentOfFloat")
        if val is not None:
            short_pct = float(val)
        fv = info.get("floatShares")
        if fv is not None:
            float_shares = float(fv)
    except Exception:
        pass

    _short_mem[symbol] = {"short_pct": short_pct, "float_shares": float_shares, "ts": time.time()}
    _save_short_mem()
    return short_pct, float_shares


def _squeeze_bonus(symbol: str, yesterday_pct: float) -> float:
    """High short interest + small float + momentum = explosive squeeze potential."""
    if yesterday_pct < 2.0:
        return 0.0
    sp, float_shares = _get_float_info(symbol)
    if sp >= 0.30:
        base = 8.0
    elif sp >= 0.20:
        base = 5.0
    elif sp >= 0.10:
        base = 2.0
    else:
        return 0.0
    if 0 < float_shares <= 10_000_000:
        return base * 2.0   # tiny float: max pain for shorts
    if float_shares <= 50_000_000:
        return base * 1.3
    return base
