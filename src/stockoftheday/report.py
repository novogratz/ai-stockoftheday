"""Telegram report builders — morning game plan + intraday watchlist (HTML)."""

from __future__ import annotations

from datetime import datetime

from .context import FuturesBias, MarketContext
from .schedule import FORCE_EXIT, LAST_ENTRY, MARKET_CLOSE, MARKET_OPEN
from .strategy import Pick

# Day-trade guardrails shown with every pick
TAKE_PROFIT_PCT = 2.5
STOP_LOSS_PCT = 1.25

_MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

_BIAS_LINES = {
    FuturesBias.GREEN: "🟢 Futures GREEN — buy at the 9:30 open",
    FuturesBias.RED: "🔴 Futures RED — wait for a bounce (~11:00 window), don't chase the open",
    FuturesBias.NEUTRAL: "⚪ Futures NEUTRAL — buy at the open, size normally",
}


def _pick_block(rank: int, p: Pick) -> str:
    medal = _MEDALS[rank] if rank < len(_MEDALS) else f"{rank + 1}."
    target = p.last_close * (1 + TAKE_PROFIT_PCT / 100)
    stop = p.last_close * (1 - STOP_LOSS_PCT / 100)
    gap = f" · gap {p.gap_pct:+.1f}%" if p.gap_pct else ""
    return (
        f"{medal} <b>{p.symbol}</b> — ${p.last_close:,.2f} | score {p.score:.1f} {p.confidence_emoji} {p.confidence}\n"
        f"    yday {p.yesterday_pct:+.1f}% · RVOL {p.rel_volume:.1f}x · ATR {p.atr_pct:.1f}%{gap}\n"
        f"    🎯 target ${target:,.2f} (+{TAKE_PROFIT_PCT}%) · 🛑 stop ${stop:,.2f} (-{STOP_LOSS_PCT}%)"
    )


def build_morning_report(
    picks: list[Pick],
    ctx: MarketContext,
    futures_bias: FuturesBias,
    futures_detail: str,
    top: int = 3,
    now: datetime | None = None,
) -> str:
    when = (now or datetime.now()).strftime("%a %b %d")
    lines = [
        f"🌅 <b>Morning Game Plan</b> — {when}",
        "",
        _BIAS_LINES[futures_bias],
        f"📈 {futures_detail}",
        f"🌡 Regime: {ctx.regime_label}",
        "",
    ]

    if not picks:
        lines.append("😴 No setups pass the filters today — sitting out is a position too.")
    else:
        lines.append(f"<b>Top {min(top, len(picks))} picks for today:</b>")
        lines.append("")
        for i, p in enumerate(picks[:top]):
            lines.append(_pick_block(i, p))
            lines.append("")

    lines += [
        f"⏰ Open {MARKET_OPEN:%H:%M} ET · last entry {LAST_ENTRY:%H:%M} · "
        f"flatten by {FORCE_EXIT:%H:%M} · close {MARKET_CLOSE:%H:%M}",
    ]
    return "\n".join(lines)


def build_intraday_report(
    picks: list[Pick],
    ctx: MarketContext,
    top: int = 3,
    now: datetime | None = None,
) -> str:
    when = (now or datetime.now()).strftime("%H:%M")
    lines = [
        f"📊 <b>Intraday Watchlist</b> — {when} ET",
        f"🌡 {ctx.regime_label}",
        "",
    ]

    if not picks:
        lines.append("😴 Nothing worth chasing right now. Protect your capital.")
    else:
        for i, p in enumerate(picks[:top]):
            lines.append(_pick_block(i, p))
            lines.append("")
        lines.append(f"⚠️ No new entries after {LAST_ENTRY:%H:%M} · flatten by {FORCE_EXIT:%H:%M} ET")

    return "\n".join(lines)
