"""NSE trading-hours check.

Approximation only: weekday + clock-time gate in IST. Does not account for
NSE holidays (e.g. a market holiday Monday-Friday is still treated as
"trading hours"), since this is a demo app's datasource switch, not a
trading calendar.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_nse_trading_hours(now: datetime | None = None) -> bool:
    """Return True if `now` (default: current time) falls within NSE trading
    hours — 9:15am-3:30pm IST, Monday-Friday."""
    moment = (now or datetime.now(IST)).astimezone(IST)
    if moment.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN <= moment.time() <= MARKET_CLOSE
