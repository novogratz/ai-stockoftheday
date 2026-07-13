# ai-stockoftheday

Momentum stock analysis + Telegram reports for day trading. Analysis only — it tells you **what** to buy and **when**; it never places orders.

Scans ~350 liquid US tickers (NYSE/NASDAQ) with a 14-signal composite score (momentum cascade, MACD, RSI, Minervini Stage 2, volume conviction, 52-week proximity, relative strength vs SPY, OBV, sector alignment, earnings blackout, short-squeeze radar, live gap), gated by a SPY×VIX market regime multiplier.

## Reports

- **Morning game plan** (8:45 ET, before the 9:30 open): futures bias (ES=F), market regime, top 3 picks with entry/target/stop.
- **Intraday watchlist** (every 30 min, 9:30–16:00 ET): top 3 picks right now, re-scored with live price gaps.

## Install

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create `.env` in the project root (get a token from @BotFather on Telegram):

```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=@yourchannel
```

## Usage

```
stockoftheday test-telegram          # verify the bot can post
stockoftheday scan --top 10          # print ranked picks in the terminal
stockoftheday scan --fast            # same, skipping slow HTTP enrichment
stockoftheday morning --notify      # send the morning game plan now
stockoftheday intraday --notify     # send an intraday watchlist update now
stockoftheday run                    # always-on scheduler (morning + every 30 min)
```

## Test

```
pytest
```

## Disclaimer

This is a screening tool, not financial advice. Day trading is risky — respect the stops.
