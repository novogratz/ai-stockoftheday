---
name: telegram-debug
description: Set up or troubleshoot Telegram delivery. Use when reports aren't arriving, the user gets a Telegram API error, or is setting up the bot token / chat id for the first time.
---

# Telegram setup & troubleshooting

Delivery is `src/stockoftheday/telegram.py` — stdlib urllib POST to the Bot API, HTML parse mode, config from `.env` at the repo root.

## First-time setup

1. User creates a bot with @BotFather in Telegram → gets `TELEGRAM_BOT_TOKEN`.
2. `TELEGRAM_CHAT_ID`: for a channel, `@channelname` (bot must be an admin of it); for a DM, the numeric id — get it by messaging the bot once, then:
   ```
   curl -s "https://api.telegram.org/bot$TOKEN/getUpdates" | python3 -m json.tool
   ```
   and read `message.chat.id`.
3. Write both into `.env` (copy `.env.example`). Never commit `.env` — it's gitignored.
4. Verify: `.venv/bin/stockoftheday test-telegram`.

## Diagnosing failures

Run `test-telegram` and read the error:

- **"Telegram not configured"** → `.env` missing/empty, or running from a different cwd is fine (path is resolved relative to the package), but the file must be at the repo root.
- **HTTP 401 Unauthorized** → bad token. Re-check with @BotFather (`/token`).
- **HTTP 400 "chat not found"** → wrong `TELEGRAM_CHAT_ID`, or the user never started a conversation with the bot (bots can't DM first), or `@channel` without the bot added as admin.
- **HTTP 400 "can't parse entities"** → malformed HTML in a report. Reports use only `<b>`/`<code>` tags; a `<`, `>`, or `&` in dynamic content must be escaped. Check recent changes to `report.py`.
- **HTTP 429** → rate limited; the run loop's 30-min cadence never hits this, so look for a crash-loop re-sending on every 60s tick.
- **URLError / timeout** → network. The run loop logs the failure and retries next cycle; nothing to fix in code.

## Scheduler-specific

`stockoftheday run` sends the morning plan once per weekday (8:45–9:30 ET window) and intraday updates every 30 min (9:30–16:00 ET). If "nothing arrives", first check the process logs — a scan exception is printed with the cycle timestamp and skips the send, and weekends/off-hours are silent by design.
