"""Tapetide MCP client for real NSE market data.

Tapetide (https://mcp.tapetide.com/mcp) is an MCP server, not a plain REST
API. This client opens an MCP streamable-HTTP connection authenticated with
a Bearer token and calls the `get_batch_quotes` tool directly — no
interactive/chat MCP usage, just a programmatic tool call from a background
polling task.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

TAPETIDE_MCP_URL = "https://mcp.tapetide.com/mcp"
BATCH_SIZE = 20  # get_batch_quotes accepts at most 20 symbols per call


class TapetideDataSource(MarketDataSource):
    """MarketDataSource backed by the Tapetide MCP server.

    Polls `get_batch_quotes` with the full watchlist every `poll_interval`
    seconds (default 2s, per Tapetide's 400 calls/day budget) and writes
    results to the PriceCache.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 2.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: Client | None = None

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        self._task = asyncio.create_task(self._run(), name="tapetide-poller")
        logger.info(
            "Tapetide poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Tapetide poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Tapetide: added ticker %s (will appear on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Tapetide: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def validate_ticker(self, ticker: str) -> bool:
        """Check `ticker` against Tapetide itself via a single-symbol quote."""
        if not self._client:
            return False
        result = await self._call_batch_quotes([ticker.upper().strip()])
        return bool(result) and result[0].get("found", False)

    # --- Internal ---

    async def _run(self) -> None:
        """Own the MCP connection for the lifetime of this task."""
        try:
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=httpx2.Timeout(30.0, read=300.0),
            ) as http_client:
                transport = streamable_http_client(TAPETIDE_MCP_URL, http_client=http_client)
                async with Client(transport) as client:
                    self._client = client
                    await self._poll_once()  # immediate first poll
                    while True:
                        await asyncio.sleep(self._interval)
                        await self._poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Tapetide poller crashed")
        finally:
            self._client = None

    async def _poll_once(self) -> None:
        """Fetch quotes for all tracked tickers (batched) and update the cache."""
        if not self._tickers:
            return

        for i in range(0, len(self._tickers), BATCH_SIZE):
            batch = self._tickers[i : i + BATCH_SIZE]
            try:
                quotes = await self._call_batch_quotes(batch)
            except Exception as e:
                logger.error("Tapetide poll failed for batch %s: %s", batch, e)
                continue

            for quote in quotes:
                # Use `requested` (the ticker we asked for) as the cache key,
                # not `symbol` — Tapetide may resolve a renamed/restructured
                # symbol (e.g. a corporate action) to a different current one.
                ticker = quote.get("requested", "").upper()
                if not quote.get("found"):
                    logger.debug("Tapetide: ticker %s not found", ticker)
                    continue
                try:
                    price = quote["price"]
                    timestamp = datetime.fromisoformat(quote["updated_at"]).timestamp()
                    self._cache.update(
                        ticker=ticker,
                        price=price,
                        timestamp=timestamp,
                        previous_close=quote.get("prev_close"),
                    )
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning("Skipping malformed quote for %s: %s", ticker, e)

    async def _call_batch_quotes(self, symbols: list[str]) -> list[dict]:
        """Call the get_batch_quotes tool and return its `data` list."""
        if not self._client:
            return []
        result = await self._client.call_tool("get_batch_quotes", {"symbols": symbols})
        payload = result.structured_content
        return payload.get("data", []) if payload else []
