"""Application reset endpoint (Reset feature)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..db import SEED_WATCHLIST
from ..portfolio import build_portfolio, portfolio_total_value

router = APIRouter(prefix="/api", tags=["system"])


@router.post("/reset")
async def post_reset(request: Request) -> dict:
    """Reset to a first-launch state: Rs 10 lakh cash, the default watchlist, and
    no positions, trades, snapshots, or chat. Reconcile the live price feed so it
    tracks exactly the default watchlist, then take a fresh startup snapshot."""
    state = request.app.state
    await state.db.reset_to_defaults()

    tracked = set(state.manager.get_tickers())
    desired = set(SEED_WATCHLIST)
    for ticker in tracked - desired:
        await state.manager.remove_ticker(ticker)
    for ticker in desired - tracked:
        await state.manager.add_ticker(ticker)

    await state.db.insert_snapshot(await portfolio_total_value(state.db, state.cache))
    return await build_portfolio(state.db, state.cache)
