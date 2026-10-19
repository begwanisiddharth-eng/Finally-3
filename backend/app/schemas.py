"""Pydantic schemas for API requests and LLM structured output."""

from __future__ import annotations

from pydantic import BaseModel


class TradeRequest(BaseModel):
    """Body of POST /api/portfolio/trade."""

    ticker: str
    quantity: float
    side: str


class WatchlistAddRequest(BaseModel):
    """Body of POST /api/watchlist."""

    ticker: str


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""

    message: str


# --- LLM structured output (section 9) ---


class LLMTrade(BaseModel):
    ticker: str
    side: str
    quantity: float


class LLMWatchlistChange(BaseModel):
    ticker: str
    action: str


class LLMResponse(BaseModel):
    """Structured output the LLM is asked to return."""

    message: str
    trades: list[LLMTrade] = []
    watchlist_changes: list[LLMWatchlistChange] = []
