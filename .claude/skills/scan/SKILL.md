---
name: scan
description: Run a market scan and explain the picks in plain language. Use when the user asks "what should I buy today", "run a scan", "any good setups?", or wants the morning/intraday picks interpreted.
---

# Market scan

Run the scanner and translate the output into a trading-decision summary, not raw numbers.

## Steps

1. Run the scan (use `--fast` unless the user wants full enrichment or it's pre-market):
   ```
   .venv/bin/stockoftheday scan --top 10 --fast
   ```
   Full enrichment (`stockoftheday scan --top 10`, no `--fast`) adds earnings blackout, squeeze bonus, and live gap — slower (several minutes), worth it before the open.

2. If the user wants the Telegram-formatted version instead: `stockoftheday morning` or `stockoftheday intraday` (add `--notify` only if they explicitly ask to send it).

3. Summarize for a day trader, per pick:
   - Why it ranked (which signals are driving the score — check RVOL, yday %, ATR, gap columns)
   - Confidence tier meaning: HIGH ≥80 (conviction setup), MEDIUM 45-80 (tradeable), LOW <45 (skip)
   - Entry plan: buy at 9:30 open if futures GREEN/NEUTRAL, wait for ~11:00 bounce if RED
   - Always state the guardrails: +2.5% target, −1.25% stop, no entries after 15:30, flat by 15:55 ET

## Caveats to surface

- Scores rank **yesterday's daily bars** + live gap; they are not tick-level intraday signals.
- A stale `data/snapshot_cache.json` (>18h) auto-refreshes; if results look identical across a day boundary, delete `data/` and re-run.
- "possibly delisted" warnings from yfinance are harmless noise for individual tickers.
- Never present picks as financial advice — it's a momentum screen.
