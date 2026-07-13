---
name: add-ticker
description: Add or remove tickers from the scan universe. Use when the user says "add TSLA to the watchlist", "scan crypto miners too", "remove delisted tickers", or wants a different universe.
---

# Manage the scan universe

The universe is `WATCHLIST` in `src/stockoftheday/universe.py` (~350 hardcoded liquid NYSE/NASDAQ tickers, grouped by theme with comment headers).

## Adding tickers

1. Add the symbol to the matching themed section of `WATCHLIST` (create a new section comment if none fits). US listings only — no exchange suffixes like `.TO`; the strategy assumes NYSE/NASDAQ hours and SPY-relative strength.
2. Also add it to `SECTOR_MAP` in the same file, mapped to the closest sector ETF (XLK tech / XLF financials / XLE energy / XLV health / XLI industrials / XLY consumer). Unmapped tickers just miss the 0-5 pt sector bonus — fine for oddballs, but map it when obvious.
3. Sanity-check the ticker resolves: `python -c "import yfinance as yf; print(yf.Ticker('SYM').history(period='5d').shape)"` — a (0, x) shape means bad/delisted symbol.
4. Delete `data/snapshot_cache.json` so the next scan fetches the new symbol.

## Removing tickers

Grep first — a symbol can appear in both `WATCHLIST` and `SECTOR_MAP`; remove it from both. Repeated "possibly delisted" warnings in scan output are the usual removal candidates.

## Duplicates

`WATCHLIST` has historically contained duplicates (harmless — prefetch dedupes via the cache dict, but they inflate the count). If touching the list anyway, check with:
```
python -c "from stockoftheday.universe import WATCHLIST as W; import collections; print([s for s,c in collections.Counter(W).items() if c>1])"
```
