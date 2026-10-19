"""Portfolio endpoints (section 8)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..portfolio import TradeError, build_portfolio, execute_trade
from ..schemas import TradeRequest

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio(request: Request) -> dict:
    state = request.app.state
    return await build_portfolio(state.db, state.cache)


@router.post("/trade")
async def post_trade(request: Request, body: TradeRequest) -> dict:
    state = request.app.state
    try:
        trade = await execute_trade(
            state.db, state.cache, state.manager, body.ticker, body.side, body.quantity
        )
    except TradeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    portfolio = await build_portfolio(state.db, state.cache)
    return {"trade": trade, "portfolio": portfolio}


@router.get("/history")
async def get_history(request: Request) -> list[dict]:
    return await request.app.state.db.list_snapshots()


@router.get("/trades")
async def get_trades(request: Request) -> list[dict]:
    return await request.app.state.db.list_trades()
