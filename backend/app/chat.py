"""LLM chat integration: prompt construction, auto-execution, SEBI enforcement.

Uses LiteLLM against Groq (groq/openai/gpt-oss-120b) with structured outputs,
per the groq-skill. LLM_MOCK=true returns deterministic responses (section 9).
"""

from __future__ import annotations

import logging
import os
import re

from litellm import completion
from tenacity import retry, stop_after_attempt, wait_exponential

from .db import Database
from .market import MarketDataError, MarketDataManager, PriceCache
from .portfolio import TradeError, build_portfolio, execute_trade
from .schemas import LLMResponse
from .watchlist import WatchlistError, add_ticker, remove_ticker

logger = logging.getLogger(__name__)

MODEL = "groq/openai/gpt-oss-120b"

SEBI_DISCLAIMER = (
    "Disclaimer: This is not financial advice. I am not a SEBI-registered research "
    "analyst or investment advisor. Please consult a qualified financial advisor "
    "before making any investment decisions."
)

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant for a simulated NSE trading workstation.

Your responsibilities:
- Analyze portfolio composition, risk concentration, and P&L.
- Suggest trades with concise, data-driven reasoning.
- Execute trades when the user asks or agrees, via the `trades` field.
- Manage the watchlist via the `watchlist_changes` field.
- Be concise and data-driven.
- Always respond with valid structured JSON matching the required schema.

You are told the data_source so your analysis is honest about whether prices are
real (tapetide) or simulated. Do NOT add any SEBI disclaimer text yourself; the
backend appends it when required.

Only tickers on the watchlist or held in the portfolio can be traded. To buy a
new ticker, add it to the watchlist in the same response (watchlist adds run
before trades)."""


class ChatError(Exception):
    """An upstream LLM failure (timeout, error, or unparseable output) -> 502."""


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
def _call_llm(**kwargs):
    return completion(**kwargs)


def _build_context(portfolio: dict, watchlist: list[dict], data_source: str) -> str:
    """Render the portfolio + watchlist context block for the prompt."""
    lines = [
        f"data_source: {data_source}",
        f"cash_balance: {portfolio['cash_balance']}",
        f"total_value: {portfolio['total_value']}",
        f"unrealized_pnl: {portfolio['unrealized_pnl']}",
        "positions:",
    ]
    if portfolio["positions"]:
        for p in portfolio["positions"]:
            lines.append(
                f"  {p['ticker']}: qty={p['quantity']} avg_cost={p['avg_cost']} "
                f"price={p['current_price']} pnl={p['unrealized_pnl']} ({p['return_percent']}%)"
            )
    else:
        lines.append("  (none)")
    lines.append("watchlist:")
    for w in watchlist:
        lines.append(f"  {w['ticker']}: {w.get('price')}")
    return "\n".join(lines)


# --- Mock mode (section 9) ---

_VERBS = {"BUY", "SELL", "ADD", "REMOVE"}


def _tokens(message: str) -> list[str]:
    """All-caps alphanumeric tokens (2+ chars), excluding the reserved verbs."""
    return [t for t in re.findall(r"[A-Z0-9]{2,}", message) if t not in _VERBS]


def _mock_response(message: str, watchlist: set[str], positions: set[str]) -> LLMResponse:
    lower = message.lower()
    tokens = _tokens(message)

    if "buy" in lower:
        for t in tokens:
            if t in watchlist:
                return LLMResponse(
                    message=f"Bought 1 share of {t} for you.",
                    trades=[{"ticker": t, "side": "buy", "quantity": 1}],
                )
    if "sell" in lower:
        for t in tokens:
            if t in positions:
                return LLMResponse(
                    message=f"Sold 1 share of {t} for you.",
                    trades=[{"ticker": t, "side": "sell", "quantity": 1}],
                )
    if "add" in lower:
        for t in tokens:
            if t not in watchlist:
                return LLMResponse(
                    message=f"Added {t} to your watchlist.",
                    watchlist_changes=[{"ticker": t, "action": "add"}],
                )
    if "remove" in lower:
        for t in tokens:
            if t in watchlist:
                return LLMResponse(
                    message=f"Removed {t} from your watchlist.",
                    watchlist_changes=[{"ticker": t, "action": "remove"}],
                )
    return LLMResponse(message="Here's your portfolio summary. How can I help you trade?")


# --- Auto-execution (section 9) ---


async def _auto_execute(
    db: Database,
    cache: PriceCache,
    manager: MarketDataManager,
    parsed: LLMResponse,
) -> list[dict]:
    """Run watchlist adds, then trades, then removals. Each action is isolated."""
    actions: list[dict] = []

    for change in parsed.watchlist_changes:
        if change.action.strip().lower() != "add":
            continue
        try:
            await add_ticker(db, manager, change.ticker)
            actions.append(_wl_action(change.ticker, "add", "executed", None))
        except (WatchlistError, MarketDataError) as e:
            actions.append(_wl_action(change.ticker, "add", "failed", str(e)))

    for trade in parsed.trades:
        try:
            result = await execute_trade(
                db, cache, manager, trade.ticker, trade.side, trade.quantity
            )
            actions.append(
                {
                    "type": "trade",
                    "ticker": result["ticker"],
                    "side": result["side"],
                    "quantity": result["quantity"],
                    "price": result["price"],
                    "status": "executed",
                    "error": None,
                }
            )
        except TradeError as e:
            actions.append(
                {
                    "type": "trade",
                    "ticker": trade.ticker.strip().upper(),
                    "side": trade.side.strip().lower(),
                    "quantity": trade.quantity,
                    "price": None,
                    "status": "failed",
                    "error": str(e),
                }
            )

    for change in parsed.watchlist_changes:
        if change.action.strip().lower() != "remove":
            continue
        await remove_ticker(db, manager, change.ticker)
        actions.append(_wl_action(change.ticker, "remove", "executed", None))

    return actions


def _wl_action(ticker: str, action: str, status: str, error: str | None) -> dict:
    return {
        "type": "watchlist",
        "ticker": ticker.strip().upper(),
        "action": action,
        "status": status,
        "error": error,
    }


async def handle_chat(
    db: Database,
    cache: PriceCache,
    manager: MarketDataManager,
    message: str,
) -> dict:
    """Process one chat turn: call the LLM, auto-execute, persist, and return
    {message, actions}. Raises ChatError on an upstream LLM failure (502)."""
    portfolio = await build_portfolio(db, cache)
    from .routes_helpers import watchlist_payload  # local import avoids cycle

    watchlist = await watchlist_payload(db, cache)
    data_source = manager.active_source_name
    history = await db.list_chat(limit=20)

    parsed = await _generate(message, portfolio, watchlist, history, data_source, db)

    actions = await _auto_execute(db, cache, manager, parsed)

    final_message = parsed.message
    if data_source == "tapetide" and SEBI_DISCLAIMER not in final_message:
        final_message = f"{final_message}\n\n{SEBI_DISCLAIMER}"

    await db.insert_chat("user", message, None)
    await db.insert_chat("assistant", final_message, actions)
    return {"message": final_message, "actions": actions}


async def _generate(
    message: str,
    portfolio: dict,
    watchlist: list[dict],
    history: list[dict],
    data_source: str,
    db: Database,
) -> LLMResponse:
    """Produce an LLMResponse via the mock or a real Groq call."""
    if os.environ.get("LLM_MOCK", "").strip().lower() == "true":
        wl = {w["ticker"] for w in watchlist}
        positions = {p["ticker"] for p in portfolio["positions"]}
        return _mock_response(message, wl, positions)

    context = _build_context(portfolio, watchlist, data_source)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current portfolio context:\n{context}"},
    ]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    try:
        import asyncio

        response = await asyncio.to_thread(
            _call_llm,
            model=MODEL,
            messages=messages,
            response_format=LLMResponse,
            reasoning_effort="low",
        )
        content = response.choices[0].message.content
        return LLMResponse.model_validate_json(content)
    except Exception as e:
        logger.exception("LLM chat generation failed")
        raise ChatError(str(e)) from e
