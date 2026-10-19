"""Watchlist add/remove logic (sections 6, 8).

Validation and the tracked-ticker rule live here so the manual API path and
the AI auto-execution path share one implementation.
"""

from __future__ import annotations

from .db import Database
from .market import MarketDataManager


class WatchlistError(Exception):
    """An unrecognized ticker was rejected (maps to HTTP 400)."""


async def add_ticker(db: Database, manager: MarketDataManager, ticker: str) -> str:
    """Add a ticker to the watchlist. Returns its added_at.

    Idempotent: re-adding a watched ticker short-circuits before validation
    (section 8), so it spends no Tapetide validation call. An unrecognized
    ticker raises WatchlistError (400); an unreachable source raises
    MarketDataError (503), handled by the caller.
    """
    ticker = ticker.strip().upper()
    existing = await db.watchlist_added_at(ticker)
    if existing is not None:
        return existing

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
