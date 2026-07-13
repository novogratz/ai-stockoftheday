"""Paper-trading ledger + $10k simulated portfolio (no real money).

Ledger: portfolio/ledger.json — one row per (date, symbol), never duplicated.
Portfolio model: the first pick recorded each day is the "stock of the day";
the whole balance buys it at the recorded price and sells at that day's close,
compounding daily. Every reported pick is tracked individually for stats.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable, Optional

import yfinance as yf

from .schedule import MARKET_CLOSE, now_et

ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_DIR = ROOT / "portfolio"
LEDGER_FILE = PORTFOLIO_DIR / "ledger.json"
START_BALANCE = 10_000.0

SETTLE_TIME = dtime(16, 5)  # run EOD settlement a few minutes after the close


def _empty_ledger() -> dict:
    return {"start_balance": START_BALANCE, "balance": START_BALANCE, "picks": []}


def load_ledger() -> dict:
    try:
        raw = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "picks" in raw:
            return raw
    except Exception:
        pass
    return _empty_ledger()


def save_ledger(ledger: dict) -> None:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def live_price_of(pick) -> float:
    """Best live-price estimate from a Pick: yesterday's close adjusted by the live gap."""
    return pick.last_close * (1 + pick.gap_pct / 100.0)


def record_picks(picks, when: datetime | None = None, ledger: dict | None = None) -> int:
    """Add picks to today's ledger rows (one per symbol per day). Returns rows added.

    The first symbol ever recorded on a day becomes the portfolio pick.
    Buy price is the live estimate at recording time — for pre-open morning
    picks that's the pre-market price, a proxy for the 9:30 open.
    """
    if not picks:
        return 0
    now = when or now_et()
    day = now.date().isoformat()
    ledger = ledger if ledger is not None else load_ledger()
    seen_today = {p["symbol"] for p in ledger["picks"] if p["date"] == day}
    has_portfolio_pick = any(
        p["date"] == day and p.get("is_portfolio_pick") for p in ledger["picks"]
    )
    added = 0
    for pick in picks:
        if pick.symbol in seen_today:
            continue
        ledger["picks"].append({
            "date": day,
            "symbol": pick.symbol,
            "buy_price": round(live_price_of(pick), 4),
            "score": pick.score,
            "close_price": None,
            "day_return_pct": None,
            "is_portfolio_pick": not has_portfolio_pick and added == 0,
        })
        seen_today.add(pick.symbol)
        added += 1
    if added:
        save_ledger(ledger)
    return added


def _fetch_close(symbol: str, day: str) -> Optional[float]:
    """Official close of `symbol` on `day` from daily bars."""
    try:
        d = date.fromisoformat(day)
        df = yf.Ticker(symbol).history(
            start=d.isoformat(), end=(d + timedelta(days=4)).isoformat(), interval="1d"
        )
        for idx, row in df.iterrows():
            if idx.date() == d:
                return float(row["Close"])
    except Exception:
        pass
    return None


def settle(
    when: datetime | None = None,
    fetch_close: Callable[[str, str], Optional[float]] = _fetch_close,
    ledger: dict | None = None,
) -> int:
    """Fill close prices/returns for unsettled picks whose session has ended
    (past days always; today only after the close). Portfolio picks compound
    into the balance in date order. Returns the number of rows settled.
    Safe to call any time — rows that can't be priced stay unsettled and are
    retried on the next call.
    """
    now = when or now_et()
    today = now.date().isoformat()
    closed_today = now.time() >= MARKET_CLOSE
    ledger = ledger if ledger is not None else load_ledger()
    unsettled = [
        p for p in ledger["picks"]
        if p["close_price"] is None
        and (p["date"] < today or (p["date"] == today and closed_today))
    ]
    settled = 0
    for p in sorted(unsettled, key=lambda x: x["date"]):
        close = fetch_close(p["symbol"], p["date"])
        if close is None or not p["buy_price"]:
            continue
        p["close_price"] = round(close, 4)
        p["day_return_pct"] = round((close - p["buy_price"]) / p["buy_price"] * 100, 3)
        if p.get("is_portfolio_pick"):
            ledger["balance"] = round(ledger["balance"] * (1 + p["day_return_pct"] / 100), 2)
        settled += 1
    if settled:
        save_ledger(ledger)
    return settled


def stats(ledger: dict | None = None) -> dict:
    ledger = ledger if ledger is not None else load_ledger()
    rows = [p for p in ledger["picks"] if p["day_return_pct"] is not None]
    wins = [p for p in rows if p["day_return_pct"] > 0]
    portfolio_days = [p for p in rows if p.get("is_portfolio_pick")]
    return {
        "picks_total": len(ledger["picks"]),
        "picks_settled": len(rows),
        "win_rate": len(wins) / len(rows) * 100 if rows else 0.0,
        "avg_day_return": sum(p["day_return_pct"] for p in rows) / len(rows) if rows else 0.0,
        "portfolio_days": len(portfolio_days),
        "balance": ledger["balance"],
        "start_balance": ledger["start_balance"],
        "total_return_pct": (ledger["balance"] - ledger["start_balance"])
        / ledger["start_balance"] * 100,
    }


def _live_price(symbol: str) -> Optional[float]:
    try:
        df = yf.Ticker(symbol).history(period="1d", interval="5m", prepost=True)
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception:
        return None


def status_lines(
    when: datetime | None = None,
    live_fetch: Callable[[str], Optional[float]] = _live_price,
    ledger: dict | None = None,
) -> list[str]:
    """Telegram lines: today's paper position + all-time portfolio standing."""
    now = when or now_et()
    today = now.date().isoformat()
    ledger = ledger if ledger is not None else load_ledger()
    lines: list[str] = []

    pick = next(
        (p for p in ledger["picks"] if p["date"] == today and p.get("is_portfolio_pick")),
        None,
    )
    display_balance = ledger["balance"]
    if pick is None:
        lines.append("📒 Today: no paper position yet")
    elif pick["day_return_pct"] is not None:
        lines.append(
            f"📒 Today: {pick['symbol']} {pick['day_return_pct']:+.2f}% (settled at close)"
        )
    else:
        live = live_fetch(pick["symbol"])
        if live and pick["buy_price"]:
            pct = (live - pick["buy_price"]) / pick["buy_price"] * 100
            display_balance = ledger["balance"] * (1 + pct / 100)
            lines.append(
                f"📒 Today: {pick['symbol']} ${pick['buy_price']:,.2f} → ${live:,.2f} ({pct:+.2f}%)"
            )
        else:
            lines.append(f"📒 Today: holding {pick['symbol']} @ ${pick['buy_price']:,.2f}")

    total_pct = (display_balance - ledger["start_balance"]) / ledger["start_balance"] * 100
    lines.append(
        f"💰 Paper portfolio: ${display_balance:,.2f} ({total_pct:+.2f}% since start, "
        f"began with ${ledger['start_balance']:,.0f})"
    )
    return lines


def build_eod_report(when: datetime | None = None, ledger: dict | None = None) -> str:
    """End-of-day Telegram recap: every pick's day return + portfolio standing."""
    now = when or now_et()
    today = now.date().isoformat()
    ledger = ledger if ledger is not None else load_ledger()
    rows = [p for p in ledger["picks"] if p["date"] == today]
    s = stats(ledger)

    lines = [f"🏁 <b>End of Day</b> — {now:%a %b %d}", ""]
    if not rows:
        lines.append("No picks were recorded today.")
    else:
        for p in sorted(rows, key=lambda x: (not x.get("is_portfolio_pick"), x["symbol"])):
            star = " ⭐" if p.get("is_portfolio_pick") else ""
            if p["day_return_pct"] is None:
                lines.append(f"• {p['symbol']}{star} — bought ${p['buy_price']:,.2f}, close pending")
            else:
                emoji = "🟢" if p["day_return_pct"] >= 0 else "🔴"
                lines.append(
                    f"{emoji} {p['symbol']}{star} — ${p['buy_price']:,.2f} → "
                    f"${p['close_price']:,.2f} ({p['day_return_pct']:+.2f}%)"
                )
    lines += [
        "",
        f"💰 Paper portfolio: ${s['balance']:,.2f} ({s['total_return_pct']:+.2f}% since start)",
        f"📈 All-time: {s['picks_settled']} picks settled · {s['win_rate']:.0f}% winners · "
        f"avg day {s['avg_day_return']:+.2f}%",
    ]
    return "\n".join(lines)
