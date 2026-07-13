---
name: add-ticker
description: Manage the scan universe. Use when the user says "add TSLA to the watchlist", "why isn't SYM being scanned?", "refresh the universe", or wants to adjust which stocks get scanned.
---

# Manage the scan universe

Two tiers in `src/stockoftheday/universe.py`:

- **Full universe (default)** — `load_universe()` fetches every NYSE/NASDAQ/NYSE American common stock (~6,000 symbols, penny stocks included) from the NASDAQ Trader symbol directory, cached 7 days in `data/us_universe.json`. Nothing to add manually — new listings appear on the next cache refresh.
- **Core list (`--core`)** — the hardcoded `WATCHLIST` (~450 liquid names), used as offline fallback and for fast scans.

## "Why isn't SYM being scanned / picked?"

Check in this order:
1. In the universe? `python -c "from stockoftheday.universe import load_universe; print('SYM' in load_universe())"`
   - Missing usually means: ETF, warrant/unit/preferred (filtered by name), dotted class share (BRK.A), or listed after the cache was built → `load_universe(refresh=True)`.
2. Passes hard filters? Price $0.30–$1000, 20d avg volume ≥ 100k, yesterday volume ≥ 50k, yesterday ≥ +0.5%, close above EMA20 (`SmartStrategy._base_ok`). Most "missing" penny stocks fail the volume bar — that's intentional.
3. Earnings within 3 days → hard-skipped by the blackout filter.

## Refreshing the universe

Delete `data/us_universe.json` or call `load_universe(refresh=True)`. The parser filters live in `parse_symbol_directory` — offline-tested in `tests/test_universe.py`; if changing a filter, extend the sample fixtures there.

## Core list edits

Add the symbol to the themed section of `WATCHLIST` **and** to `SECTOR_MAP` (closest sector ETF: XLK/XLF/XLE/XLV/XLI/XLY — unmapped just misses the 0-5 pt sector bonus). US listings only, no exchange suffixes. Sanity-check it resolves:
```
python -c "import yfinance as yf; print(yf.Ticker('SYM').history(period='5d').shape)"
```
