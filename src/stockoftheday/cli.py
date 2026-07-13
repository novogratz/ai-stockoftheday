"""CLI — scan, morning/intraday reports, and the always-on scheduler loop."""

from __future__ import annotations

import argparse
import sys
import time as _time
from datetime import datetime

from .context import MarketContext, get_futures_bias
from .market_data import MarketData
from .portfolio import (
    SETTLE_TIME,
    build_eod_report,
    record_picks,
    settle,
    stats as portfolio_stats,
    status_lines,
)
from .report import build_intraday_report, build_morning_report
from .schedule import MARKET_OPEN, is_market_session, is_morning_window, is_weekday, now_et
from .strategy import Pick, SmartStrategy
from .telegram import TelegramConfigError, send_message
from .universe import WATCHLIST, load_universe

INTRADAY_INTERVAL = 30 * 60  # seconds between intraday watchlist updates


def _progress(done: int, total: int) -> None:
    print(f"\r  downloading {done}/{total} tickers...", end="", flush=True)
    if done >= total:
        print()


def _universe(args: argparse.Namespace) -> list[str]:
    if getattr(args, "core", False):
        return WATCHLIST
    return load_universe()


def _run_scan(
    watchlist: list[str],
    md: MarketData | None = None,
    enrich: bool = True,
) -> tuple[list[Pick], SmartStrategy]:
    md = md or MarketData()
    print(f"Scanning {len(watchlist)} tickers...")
    md.prefetch(watchlist, progress_cb=_progress)
    strategy = SmartStrategy(market_data=md)
    picks = strategy.scan(watchlist, enrich=enrich)
    return picks, strategy


def _notify(text: str) -> bool:
    try:
        send_message(text)
        return True
    except TelegramConfigError as exc:
        print(f"Telegram not configured: {exc}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"Telegram send failed: {exc}", file=sys.stderr)
    return False


def cmd_scan(args: argparse.Namespace) -> int:
    picks, _ = _run_scan(_universe(args), enrich=not args.fast)
    if not picks:
        print("No picks pass the filters today.")
        return 0
    print(f"\n{'#':>3}  {'SYM':<6}{'PRICE':>10}{'SCORE':>8}  {'CONF':<7}"
          f"{'YDAY%':>7}{'RVOL':>6}{'ATR%':>6}{'GAP%':>7}")
    for i, p in enumerate(picks[: args.top], 1):
        print(f"{i:>3}  {p.symbol:<6}{p.last_close:>10,.2f}{p.score:>8.1f}  {p.confidence:<7}"
              f"{p.yesterday_pct:>7.1f}{p.rel_volume:>6.1f}{p.atr_pct:>6.1f}{p.gap_pct:>7.1f}")
    return 0


def _with_portfolio(text: str, picks: list[Pick], top: int) -> str:
    """Record today's reported picks in the paper ledger and append its status."""
    try:
        settle()  # lazily settle any past unsettled days first
        record_picks(picks[:top])
        return text + "\n\n" + "\n".join(status_lines())
    except Exception as exc:
        print(f"portfolio tracking failed: {exc}", file=sys.stderr)
        return text


def cmd_morning(args: argparse.Namespace) -> int:
    picks, strategy = _run_scan(_universe(args))
    bias, detail = get_futures_bias()
    text = build_morning_report(picks, strategy.ctx, bias, detail, top=args.top)
    text = _with_portfolio(text, picks, args.top)
    print(text)
    if args.notify:
        return 0 if _notify(text) else 1
    return 0


def cmd_intraday(args: argparse.Namespace) -> int:
    picks, strategy = _run_scan(_universe(args))
    text = build_intraday_report(picks, strategy.ctx, top=args.top)
    text = _with_portfolio(text, picks, args.top)
    print(text)
    if args.notify:
        return 0 if _notify(text) else 1
    return 0


def cmd_portfolio(args: argparse.Namespace) -> int:
    settle()
    s = portfolio_stats()
    print(f"Paper portfolio: ${s['balance']:,.2f} ({s['total_return_pct']:+.2f}% since start, "
          f"began with ${s['start_balance']:,.0f})")
    print(f"Picks recorded: {s['picks_total']} · settled: {s['picks_settled']} · "
          f"win rate: {s['win_rate']:.0f}% · avg day return: {s['avg_day_return']:+.2f}% · "
          f"portfolio days: {s['portfolio_days']}")
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    n = settle()
    print(f"Settled {n} pick(s).")
    return 0


def cmd_test_telegram(args: argparse.Namespace) -> int:
    ok = _notify("✅ <b>stockoftheday</b> is connected. Reports will land here.")
    print("Sent." if ok else "Failed.")
    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    """
    Always-on loop (ET clock, weekdays only):
      - on startup  → one report immediately (intraday if the market is open, game plan otherwise)
      - 8:45-9:30   → one morning game plan
      - 9:30-16:00  → intraday watchlist every 30 min
    """
    print("Scheduler running (Ctrl-C to stop). Startup report now, morning plan 8:45 ET, intraday every 30 min 9:30-16:00.")
    universe = _universe(args)
    last_morning_date: str | None = None
    last_intraday = 0.0

    # Daily bars don't change during a session, so one MarketData per calendar
    # day: the first scan downloads everything, later cycles reuse the frames
    # and only the live gap data is refetched inside strategy.scan().
    md: MarketData | None = None
    md_date: str | None = None

    def _daily_md(today: str) -> MarketData:
        nonlocal md, md_date
        if md is None or md_date != today:
            md = MarketData()
            md_date = today
        return md

    last_settle_date: str | None = None

    # Startup report: the in-session case is covered by the first loop tick
    # (last_intraday == 0), so only the out-of-session case needs handling here.
    start = now_et()
    if not is_market_session(start):
        try:
            print(f"[{start:%H:%M}] startup — building stock-of-the-day game plan...")
            picks, strategy = _run_scan(universe, md=_daily_md(start.date().isoformat()))
            bias, detail = get_futures_bias()
            text = build_morning_report(picks, strategy.ctx, bias, detail, top=args.top)
            text = _with_portfolio(text, picks, args.top)
            _notify(text)
            print(f"[{start:%H:%M}] startup game plan sent.")
            if is_weekday(start) and start.time() < MARKET_OPEN:
                last_morning_date = start.date().isoformat()  # don't resend at 8:45
        except Exception as exc:
            print(f"[{start:%H:%M}] startup report failed: {exc}", file=sys.stderr)

    while True:
        now = now_et()
        today = now.date().isoformat()
        try:
            if is_morning_window(now) and last_morning_date != today:
                print(f"[{now:%H:%M}] building morning game plan...")
                picks, strategy = _run_scan(universe, md=_daily_md(today))
                bias, detail = get_futures_bias()
                text = build_morning_report(picks, strategy.ctx, bias, detail, top=args.top)
                text = _with_portfolio(text, picks, args.top)
                _notify(text)
                last_morning_date = today
                print(f"[{now:%H:%M}] morning game plan sent.")

            elif is_market_session(now) and _time.time() - last_intraday >= INTRADAY_INTERVAL:
                print(f"[{now:%H:%M}] building intraday watchlist...")
                picks, strategy = _run_scan(universe, md=_daily_md(today))
                text = build_intraday_report(picks, strategy.ctx, top=args.top)
                text = _with_portfolio(text, picks, args.top)
                _notify(text)
                last_intraday = _time.time()
                print(f"[{now:%H:%M}] intraday watchlist sent.")

            elif (is_weekday(now) and now.time() >= SETTLE_TIME
                  and last_settle_date != today):
                print(f"[{now:%H:%M}] settling today's picks...")
                settle()
                _notify(build_eod_report())
                last_settle_date = today
                print(f"[{now:%H:%M}] end-of-day recap sent.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[{now:%H:%M}] cycle failed: {exc}", file=sys.stderr)

        _time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="stockoftheday",
        description="Momentum stock analysis + Telegram day-trading reports (no order execution).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    core_help = "scan only the ~450 hardcoded liquid names instead of the full US listing"

    scan = sub.add_parser("scan", help="scan the universe and print ranked picks")
    scan.add_argument("--top", type=int, default=10, help="number of picks to print")
    scan.add_argument("--fast", action="store_true", help="skip earnings/squeeze/gap enrichment (no extra HTTP)")
    scan.add_argument("--core", action="store_true", help=core_help)
    scan.set_defaults(func=cmd_scan)

    morning = sub.add_parser("morning", help="build the pre-open morning game plan")
    morning.add_argument("--top", type=int, default=3)
    morning.add_argument("--notify", action="store_true", help="send to Telegram")
    morning.add_argument("--core", action="store_true", help=core_help)
    morning.set_defaults(func=cmd_morning)

    intraday = sub.add_parser("intraday", help="build the intraday watchlist update")
    intraday.add_argument("--top", type=int, default=3)
    intraday.add_argument("--notify", action="store_true", help="send to Telegram")
    intraday.add_argument("--core", action="store_true", help=core_help)
    intraday.set_defaults(func=cmd_intraday)

    run = sub.add_parser("run", help="always-on loop: morning plan at 8:45 ET + intraday updates every 30 min")
    run.add_argument("--top", type=int, default=3)
    run.add_argument("--core", action="store_true", help=core_help)
    run.set_defaults(func=cmd_run)

    portfolio = sub.add_parser("portfolio", help="show paper portfolio stats ($10k simulation)")
    portfolio.set_defaults(func=cmd_portfolio)

    settle_cmd = sub.add_parser("settle", help="fetch closes for unsettled ledger picks")
    settle_cmd.set_defaults(func=cmd_settle)

    test = sub.add_parser("test-telegram", help="send a test message to verify the bot token/chat id")
    test.set_defaults(func=cmd_test_telegram)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except KeyboardInterrupt:
        print("\nbye")
        sys.exit(130)


if __name__ == "__main__":
    main()
