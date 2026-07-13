# ai-stockoftheday

Momentum stock analysis + Telegram reports for day trading. Analysis only — it tells you **what** to buy and **when**; it never places orders.

Scans the **full US listing** (~6,000 NYSE/NASDAQ/NYSE American common stocks, penny stocks included), scores each with a 14-signal composite, and posts the best setups to Telegram before the open and every 30 minutes during the session.

The universe comes from the official NASDAQ Trader symbol directory (ETFs, warrants, preferreds, and test issues filtered out), cached for 7 days in `data/us_universe.json`. Pass `--core` to any command to scan only the ~450 hardcoded liquid names instead. Price floor is $0.30, so anything liquid enough (≥100k avg daily volume) competes.

## The 14-signal engine (0–~140 pts)

Synthesized from IBKR, Minervini, CANSLIM, and LangChain quant strategies:

| # | Signal | Max pts |
|---|--------|---------|
| A | Momentum cascade — 1d/5d/20d alignment | 25 |
| B | MACD(12,26,9) — bullish crossover | 12 |
| C | RSI(14) — momentum zone 45–70 | 10 |
| D | Stage 2 MA alignment — Price > SMA50 > SMA150 > SMA200 | 12 |
| E | Volume conviction — RVOL + trend + 1-year volume record | 18 |
| F | 52-week high proximity — within 20% of high (CANSLIM "N") | 10 |
| G | Relative strength vs SPY — outperforms 5d return | 8 |
| H | OBV smart money — volume-weighted direction | 5 |
| I | Bonuses — close quality + ATR + Yahoo trending | 10 |
| J | Sector alignment — stock in a hot sector (XLK/XLF/XLE…) | 5 |
| K | **Earnings blackout** — hard filter: skip if earnings ≤ 3 days | — |
| L | Short squeeze radar — float-adjusted short interest | 16 |
| M | Live gap — pre-market/intraday move vs yesterday's close | −18 to +20 |
| N | Consecutive green days — 2–3 = sweet spot, 5+ = penalty | −8 to +6 |

**Market regime gate:** every score is multiplied by a combined SPY-trend × VIX factor (0.55–1.12). SPY below its SMA200 or VIX ≥ 30 slashes everything — never fight the tape.

**Confidence tiers:** HIGH ≥ 80 · MEDIUM ≥ 45 · LOW < 45.

## Daily schedule (ET, weekdays — `stockoftheday run`)

| Time | Report |
|------|--------|
| 8:45 AM | 🌅 Morning game plan: ES=F futures bias, market regime, top 3 picks with entry/target/stop |
| 9:30 AM – 4:00 PM | 📊 Intraday watchlist every 30 min, re-scored with live price gaps |
| 3:30 PM | Last-entry cutoff (stated in every report) |
| 3:55 PM | Flatten-everything reminder (stated in every report) |

Every pick ships with fixed day-trade guardrails: **+2.5% target, −1.25% stop**.

## Paper portfolio ($10k simulation)

Every reported pick is recorded in a local ledger (`portfolio/ledger.json`) — one row per ticker per day: date, buy price (live price when first reported), official close, day return. A simulated portfolio starts at **$10,000**, goes all-in on the first pick of each day (the ⭐ stock of the day), and sells at the close, compounding daily.

- Every 30-min Telegram update ends with today's position P&L and the all-time balance
- After the close (~16:05 ET) the run loop settles the day and sends a 🏁 recap with every pick's return
- `stockoftheday portfolio` prints the stats any time; `stockoftheday settle` back-fills missed days

No real money moves — it's a months-long paper test of whether the picks have edge. Back up `portfolio/ledger.json` if you care about the history (it's gitignored).

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
stockoftheday scan --core            # only the ~450 hardcoded liquid names
stockoftheday morning --notify       # send the morning game plan now
stockoftheday intraday --notify      # send an intraday watchlist update now
stockoftheday run                    # always-on scheduler (morning + every 30 min + EOD recap)
stockoftheday portfolio              # paper portfolio stats
stockoftheday settle                 # back-fill closes for unsettled ledger picks
```

## Test

```
pytest
```

The suite is fully offline — synthetic price data, no network.

## Claude Code skills

The repo ships project skills under `.claude/skills/` for working on it with [Claude Code](https://claude.com/claude-code):

- **/scan** — run a scan and get the picks explained in plain language
- **/add-signal** — add or reweight a scoring signal the right way (pure signals, offline tests, doc sync)
- **/add-ticker** — extend or prune the universe + sector map
- **/telegram-debug** — set up the bot or diagnose delivery failures

## Disclaimer

This is a screening tool, not financial advice. Scores rank yesterday's daily bars plus a live gap adjustment — not tick-level intraday signals. Day trading is risky — respect the stops.
