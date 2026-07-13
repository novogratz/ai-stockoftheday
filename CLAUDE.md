# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```
pip install -e ".[dev]"          # install package + pytest in editable mode
pytest                           # run the full test suite (offline, no network)
pytest tests/test_strategy.py::test_bear_regime_scores_lower_than_bull  # single test
stockoftheday scan --top 10      # scan universe, print ranked picks (network)
stockoftheday scan --fast        # skip earnings/squeeze/gap HTTP enrichment
stockoftheday morning --notify   # morning game plan → Telegram
stockoftheday intraday --notify  # intraday watchlist → Telegram
stockoftheday run                # always-on scheduler loop
stockoftheday test-telegram      # verify TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

Telegram needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` at the repo root (see `.env.example`). There is no linter or type checker configured.

## What this is

Analysis-and-reporting only: it scans a US stock universe, ranks day-trade candidates, and posts reports to Telegram. It **never places orders** — that scope is deliberate (the logic was ported from `~/ai-wealthsimple-bot`, leaving the broker-automation code behind). Don't add order execution.

## Architecture

Pipeline: `universe` → `market_data` → `signals` + `context` → `strategy` → `report` → `telegram`, orchestrated by `cli`.

- `universe.py` — `WATCHLIST` (~350 hardcoded liquid NYSE/NASDAQ tickers) and `SECTOR_MAP` (symbol → sector ETF).
- `market_data.py` — `MarketData.prefetch()` batch-downloads 1y daily bars via `yf.download`, builds frozen `Snapshot` dataclasses (yesterday's OHLCV stats, ATR14, EMA5/20). Snapshots persist to `data/snapshot_cache.json` (18h TTL); raw frames are memory-only, so signal computation needs a prefetch in the same process.
- `signals.py` — pure functions: `build_signals(df)` computes the 9-indicator `Signals` dataclass (RSI14, MACD cross, SMA50/150/200, 52w high, OBV, volume trend, consecutive green days) from an OHLCV frame. No I/O — keep it that way for testability.
- `context.py` — `MarketContext` (SPY trend vs SMA50/200, sector ETF returns, VIX, Yahoo trending) whose `regime_multiplier` (0.55–1.12) scales every score; `get_futures_bias()` reads ES=F for the morning GREEN/RED/NEUTRAL call. Both cache under `data/`.
- `strategy.py` — `SmartStrategy.scan()` applies hard filters (`_base_ok`), the 14-signal `_score()`, then three enrichment passes that hit the network: earnings blackout (hard skip, top 50 only), short-squeeze bonus, and live gap adjustment via parallel 5m prepost fetches. `scan(enrich=False)` skips all network enrichment — tests rely on this plus injected fake `market_data`/`ctx`.
- `report.py` — pure formatters producing Telegram HTML: morning game plan and intraday watchlist, with fixed target (+2.5%) / stop (−1.25%) guardrails per pick.
- `schedule.py` — ET market clock (`America/New_York`): session 9:30–16:00, morning window 8:45–9:30, last entry 15:30, force exit 15:55.
- `cli.py` — subcommands plus `run`, a 60s-tick loop that sends one morning report per weekday and an intraday report every 30 min during the session. Each cycle builds a fresh `MarketData` so gap enrichment reflects live prices.

`data/` (caches) and `.env` are gitignored — never commit them.

## Project skills

`.claude/skills/` holds repo-specific skills — prefer them over improvising:

- `scan` — run a scan and interpret picks for the user (confidence tiers, entry plan, guardrails)
- `add-signal` — the correct path for new/tuned scoring signals (signals.py vs strategy.py split, point budgets, offline tests, doc sync)
- `add-ticker` — universe/SECTOR_MAP edits and delisted-ticker cleanup
- `telegram-debug` — bot setup and delivery-failure diagnosis

## Testing conventions

Tests are fully offline: synthetic OHLCV DataFrames for `signals`/`market_data`, a `FakeMarketData` + hand-built `MarketContext` injected into `SmartStrategy` with `enrich=False`, and direct string assertions on report output. Any new scoring or formatting logic should stay testable without network access.
