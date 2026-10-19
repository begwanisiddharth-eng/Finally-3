"""Watchlist endpoints (section 8)."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request

from ..market import MarketDataError
from ..routes_helpers import watchlist_payload
from ..schemas import WatchlistAddRequest
from ..watchlist import WatchlistError, add_ticker, remove_ticker

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def get_watchlist(request: Request) -> dict:
    state = request.app.state
    return {"tickers": await watchlist_payload(state.db, state.cache)}


@router.post("")
async def post_watchlist(request: Request, body: WatchlistAddRequest) -> dict:
    state = request.app.state
    try:
        added_at = await add_ticker(state.db, state.manager, body.ticker)
    except WatchlistError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MarketDataError as e:
        raise HTTPException(status_code=503, detail="Couldn't check this ticker right now.") from e
    return {"ticker": body.ticker.strip().upper(), "added_at": added_at}


@router.delete("/{ticker}")
async def delete_watchlist(request: Request, ticker: str) -> dict:
    state = request.app.state
    ticker = unquote(ticker).strip().upper()
    removed = await remove_ticker(state.db, state.manager, ticker)
    return {"ticker": ticker, "removed": removed}
