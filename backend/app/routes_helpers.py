"""Shared response-shaping helpers used by more than one route/module."""

from __future__ import annotations

from .db import Database
from .market import PriceCache


async def watchlist_payload(db: Database, cache: PriceCache) -> list[dict]:
    """Watchlist tickers with latest prices, ordered by added_at (section 8).

    Membership comes from the watchlist table; prices come from the cache. A
    just-added ticker with no price yet reports nulls for the price fields.
    """
    result = []
    for ticker in await db.list_watchlist():
        update = cache.get(ticker)
        if update is None:
            result.append(
                {
                    "ticker": ticker,
                    "price": None,
                    "previous_close": None,
                    "day_change": None,
                    "day_change_percent": None,
                    "direction": None,
                    "timestamp": None,
                }
            )
        else:
            result.append(
                {
                    "ticker": ticker,
                    "price": update.price,
                    "previous_close": update.previous_close,
                    "day_change": update.day_change,
                    "day_change_percent": update.day_change_percent,
                    "direction": update.direction,
                    "timestamp": update.timestamp,
                }
            )
    return result
