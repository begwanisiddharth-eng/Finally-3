"""Portfolio valuation and trade execution (sections 7, 8)."""

from __future__ import annotations

import math

from .db import Database
from .market import MarketDataManager, PriceCache

EPSILON = 1e-9  # float tolerance for "zero shares" and "insufficient shares"


class TradeError(Exception):
    """A trade failed validation (maps to HTTP 400)."""


async def build_portfolio(db: Database, cache: PriceCache) -> dict:
    """Current cash, positions with live valuation, and totals (section 8)."""
    cash = await db.get_cash()
    positions = []
    positions_value = 0.0
    total_unrealized = 0.0

    for pos in await db.list_positions():
        ticker = pos["ticker"]
        qty = pos["quantity"]
        avg_cost = pos["avg_cost"]
        price = cache.get_price(ticker)

        if price is None:
            # No cached price yet (e.g. Tapetide's first poll pending): fall
            # back to cost basis so nothing is valued at zero (section 8).
            market_value = qty * avg_cost
            unrealized = 0.0
            return_percent = 0.0
        else:
            market_value = qty * price
            unrealized = (price - avg_cost) * qty
            return_percent = (price - avg_cost) / avg_cost * 100 if avg_cost else 0.0

        positions_value += market_value
        total_unrealized += unrealized
        positions.append(
            {
                "ticker": ticker,
                "quantity": qty,
                "avg_cost": round(avg_cost, 2),
                "current_price": None if price is None else round(price, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized, 2),
                "return_percent": round(return_percent, 2),
            }
        )

    return {
        "cash_balance": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(cash + positions_value, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "positions": positions,
    }


async def portfolio_total_value(db: Database, cache: PriceCache) -> float:
    """Total portfolio value (cash + positions) for a snapshot."""
    portfolio = await build_portfolio(db, cache)
    return portfolio["total_value"]


def _validate_quantity(quantity: float) -> None:
    if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
        raise TradeError("Quantity must be a number.")
    if not math.isfinite(quantity) or quantity <= 0:
        raise TradeError("Quantity must be a positive number.")


async def execute_trade(
    db: Database,
    cache: PriceCache,
    manager: MarketDataManager,
    ticker: str,
    side: str,
    quantity: float,
) -> dict:
    """Validate and execute a market order. Returns the recorded trade dict.

    Raises TradeError for any validation failure (section 8).
    """
    ticker = ticker.strip().upper()
    side = side.strip().lower()
    _validate_quantity(quantity)

    if side not in ("buy", "sell"):
        raise TradeError("Side must be 'buy' or 'sell'.")

    if ticker not in set(manager.get_tickers()):
        raise TradeError(
            "Only tickers in your watchlist or held in your portfolio can be traded. "
            f"Add {ticker} to your watchlist first."
        )

    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker} yet - try again in a moment.")

    position = await db.get_position(ticker)

    if side == "buy":
        cost = quantity * price
        cash = await db.get_cash()
        if cost > cash + EPSILON:
            raise TradeError("Insufficient cash for this purchase.")
        await db.set_cash(cash - cost)
        if position:
            old_qty = position["quantity"]
            old_avg = position["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = (old_qty * old_avg + quantity * price) / new_qty
            await db.upsert_position(ticker, new_qty, new_avg)
        else:
            await db.upsert_position(ticker, quantity, price)
    else:  # sell
        held = position["quantity"] if position else 0.0
        if quantity > held + EPSILON:
            raise TradeError("Insufficient shares for this sale.")
        cash = await db.get_cash()
        await db.set_cash(cash + quantity * price)
        remaining = held - quantity
        if abs(remaining) < EPSILON:
            await db.delete_position(ticker)
            # Position zeroed: stop pricing the ticker if it is not watched
            # (tracked = watchlist U positions, section 6).
            if ticker not in await db.list_watchlist():
                await manager.remove_ticker(ticker)
        else:
            await db.upsert_position(ticker, remaining, position["avg_cost"])

    trade = await db.insert_trade(ticker, side, quantity, round(price, 2))
    trade["price"] = round(price, 2)
    await db.insert_snapshot(await portfolio_total_value(db, cache))
    return trade
