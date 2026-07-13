---
name: add-signal
description: Add or tune a scoring signal in the 14-signal strategy. Use when the user wants a new indicator (e.g. VWAP, gap-and-go, news catalyst), wants to reweight an existing signal, or asks why a stock scored the way it did.
---

# Add or tune a scoring signal

The score pipeline: `signals.py` computes indicators from OHLCV → `strategy.py:_score()` converts them to points → regime multiplier scales the total. Keep that separation.

## Where things go

- **New indicator from price/volume history** → add a field to the `Signals` dataclass and compute it in `build_signals()` (`src/stockoftheday/signals.py`). Pure function, no I/O.
- **Points for the indicator** → add a lettered block in `SmartStrategy._score()` (`src/stockoftheday/strategy.py`). Follow the existing style: tiered thresholds, small point budgets (5-25 pts max per signal).
- **Hard filter** (disqualifies rather than scores) → add to `_base_ok()` or, if it needs HTTP (like earnings), to the enrichment section of `scan()` guarded by the top-50 limit.
- **Data needing HTTP beyond daily bars** (short float, earnings, live quotes) → follow the pattern of `_get_float_info`: module-level memory dict + JSON cache under `data/` with a TTL, wrapped in try/except returning a safe default.

## Rules

1. Point budgets matter: total max is ~140. A new signal worth more than 15 pts will dominate — justify it or scale it down.
2. Anything network-touching must be skippable via `scan(enrich=False)` so tests stay offline.
3. Add an offline test in `tests/test_strategy.py` (use the existing `FakeMarketData` + `_ctx()` helpers) or `tests/test_signals.py` (synthetic DataFrame). Craft a case where the new signal flips the ranking between two candidates.
4. Update the signal table in the `SmartStrategy` docstring, `README.md`, and `CLAUDE.md`'s architecture section.
5. Run `pytest` — everything must pass without network.

## Explaining a score

To break down why a ticker scored X: rebuild its snapshot + signals in a Python snippet (`MarketData().snapshot(sym)`, `build_signals(md.get_frame(sym))` after a prefetch) and walk the lettered blocks in `_score()` manually, showing points per signal.
