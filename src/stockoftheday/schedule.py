"""US market clock (Eastern Time) — session windows for the report scheduler."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
MORNING_REPORT = time(8, 45)   # game plan lands before the open
LAST_ENTRY = time(15, 30)      # no fresh entries after this
FORCE_EXIT = time(15, 55)      # flatten everything before the close


def now_et() -> datetime:
    return datetime.now(MARKET_TZ)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def is_market_session(dt: datetime) -> bool:
    return is_weekday(dt) and MARKET_OPEN <= dt.time() <= MARKET_CLOSE


def is_morning_window(dt: datetime) -> bool:
    """Between the morning-report time and the open — when the game plan should go out."""
    return is_weekday(dt) and MORNING_REPORT <= dt.time() < MARKET_OPEN
