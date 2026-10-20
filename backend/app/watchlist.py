"""Watchlist add/remove logic (sections 6, 8).

Validation and the tracked-ticker rule live here so the manual API path and
the AI auto-execution path share one implementation.
"""

from __future__ import annotations

from .db import Database
from .market import MarketDataManager

MAX_WATCHLIST = 20  # hard cap on watchlist size


class WatchlistError(Exception):
    """A watchlist add was rejected (unrecognized ticker or cap reached); maps to HTTP 400."""


async def add_ticker(db: Database, manager: MarketDataManager, ticker: str) -> str:
    """Add a ticker to the watchlist. Returns its added_at.

    Idempotent: re-adding a watched ticker short-circuits before validation
    (section 8), so it spends no Tapetide validation call and is allowed even at
    the cap. A new ticker beyond MAX_WATCHLIST raises WatchlistError (400); so
    does an unrecognized ticker. An unreachable source raises MarketDataError
    (503), handled by the caller.
    """
    ticker = ticker.strip().upper()
    existing = await db.watchlist_added_at(ticker)
    if existing is not None:
        return existing

    if len(await db.list_watchlist()) >= MAX_WATCHLIST:
        raise WatchlistError(f"The watchlist can only contain {MAX_WATCHLIST} shares")

    if not await manager.validate_ticker(ticker):
        raise WatchlistError(f"No stock with ticker {ticker} exists")

    added_at = await db.add_watchlist(ticker)
    await manager.add_ticker(ticker)
    return added_at


async def remove_ticker(db: Database, manager: MarketDataManager, ticker: str) -> bool:
    """Remove a ticker from the watchlist. Returns True if a row was deleted.

    Idempotent (section 8). The price source keeps pricing the ticker if it is
    still held in a position (tracked = watchlist U positions, section 6).
    """
    ticker = ticker.strip().upper()
    removed = await db.remove_watchlist(ticker)
    if await db.get_position(ticker) is None:
        await manager.remove_ticker(ticker)
    return removed
