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
from zoneinfo import ZoneInfo

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .cache import PriceCache
from .interface import MarketDataError, MarketDataSource

logger = logging.getLogger(__name__)

TAPETIDE_MCP_URL = "https://mcp.tapetide.com/mcp"
DEFAULT_MAX_FAILURES = 3  # consecutive failures before the source reports degraded
BATCH_SIZE = 20  # get_batch_quotes accepts at most 20 symbols per call
TAPETIDE_CALL_TIMEOUT = 10.0  # hard cap per tool call (seconds), so a hang becomes a failure
IST = ZoneInfo("Asia/Kolkata")


class TapetideToolError(MarketDataError):
    """Tapetide was reached, but the tool call returned is_error=True (quota, auth,
    server error). A MarketDataError, so the API maps it to 503 ("couldn't check"),
    never a 400 "no such ticker" (PLAN.md section 6)."""


def _error_text(result) -> str:
    """Extract a human-readable message from an is_error CallToolResult."""
    parts = [getattr(c, "text", "") for c in (result.content or [])]
    return " ".join(p for p in parts if p) or "unknown tool error"


def _parse_timestamp(value: str) -> float:
    """Parse an ISO-8601 timestamp to Unix seconds, assuming IST if naive.

    Tapetide's `updated_at` is normally offset-aware. If an upstream value ever
    arrives naive (no offset), it is assumed to be IST rather than interpreted
    in the server's local zone, which would silently shift display times on a
    non-IST machine (§7).
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.timestamp()


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
        max_failures: int = DEFAULT_MAX_FAILURES,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: Client | None = None
        # The poll loop and validate_ticker share one MCP Client; serialize all
        # tool calls so they are never issued concurrently on it (§6).
        self._call_lock = asyncio.Lock()
        # Degraded-mode tracking (§6): consecutive poll failures, plus a dead
        # poll task (which stops producing per-batch failures altogether).
        self._max_failures = max_failures
        self._consecutive_failures = 0
        self._stopped = False

    def is_degraded(self) -> bool:
        """True after N consecutive poll failures, or if the poll task died."""
        if self._consecutive_failures >= self._max_failures:
            return True
        return self._task is not None and self._task.done() and not self._stopped

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        self._stopped = False
        self._consecutive_failures = 0
        self._task = asyncio.create_task(self._run(), name="tapetide-poller")
        logger.info(
            "Tapetide poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        self._stopped = True
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
        """Check `ticker` against Tapetide itself via a single-symbol quote.

        Returns True/False only when Tapetide was actually reached. Raises
        `MarketDataError` on a transport/connection failure (including no live
        client), so the caller does not mistake "couldn't check" for "invalid
        symbol" (§6).

        On a successful validation the fetched quote is written to the cache, so
        a watchlist add immediately followed by a trade (the one-turn
        "add X and buy 10" flow, §9) has a fill price without waiting for the
        next poll.
        """
        # _call_batch_quotes raises MarketDataError on any failure (no client,
        # timeout, transport error, or an is_error tool result), so a transport
        # or quota problem surfaces as 503, never as a false "not found" 400.
        quotes = await self._call_batch_quotes([ticker.strip().upper()])
        if not quotes or not quotes[0].get("found", False):
            return False
        self._cache_quote(quotes[0])
        return True

    # --- Internal ---

    async def _run(self) -> None:
        """Own the MCP connection for the lifetime of this task."""
        try:
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=httpx2.Timeout(30.0, read=60.0),
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
        tickers = list(self._tickers)  # snapshot: add/remove may run mid-poll
        if not tickers:
            return

        poll_failed = False
        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i : i + BATCH_SIZE]
            try:
                quotes = await self._call_batch_quotes(batch)
            except MarketDataError as e:
                logger.error("Tapetide poll failed for batch %s: %s", batch, e)
                poll_failed = True
                continue

            for quote in quotes:
                # A ticker removed mid-poll must not be written back into the
                # cache (would leave a ghost row in the SSE frame).
                if quote.get("requested", "").upper() in self._tickers:
                    self._cache_quote(quote)

        # One failure per poll cycle, however many batches failed; a fully
        # successful cycle resets the streak.
        self._consecutive_failures = self._consecutive_failures + 1 if poll_failed else 0

    def _cache_quote(self, quote: dict) -> bool:
        """Parse one get_batch_quotes entry and write it to the cache.

        Returns True if a price was written, False for a `found: false` or
        malformed quote. Shared by the poll loop and `validate_ticker`.
        """
        # Use `requested` (the ticker we asked for) as the cache key, not
        # `symbol` — Tapetide may resolve a renamed/restructured symbol (e.g. a
        # corporate action) to a different current one.
        ticker = quote.get("requested", "").upper()
        if not quote.get("found"):
            logger.debug("Tapetide: ticker %s not found", ticker)
            return False
        try:
            self._cache.update(
                ticker=ticker,
                price=quote["price"],
                timestamp=_parse_timestamp(quote["updated_at"]),
                previous_close=quote.get("prev_close"),
            )
            return True
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Skipping malformed quote for %s: %s", ticker, e)
            return False

    async def _call_tool(self, name: str, arguments: dict) -> dict:
        """One serialized, time-bounded tool call. Returns structured_content (or {}).

        The MCP SDK does not raise on a tool-level failure: `call_tool` returns a
        CallToolResult with `is_error=True`. If that is not inspected, a quota/auth
        error looks like empty data (never counted as a failure, feed freezes
        silently) and `validate_ticker` answers False -> a wrong 400 instead of
        503 (PLAN.md section 6). So this wrapper raises MarketDataError for a
        missing client, timeout, transport exception, or an is_error result.
        """
        client = self._client
        if client is None:
            raise MarketDataError("Tapetide client is not connected")
        async with self._call_lock:
            try:
                result = await asyncio.wait_for(
                    client.call_tool(name, arguments), timeout=TAPETIDE_CALL_TIMEOUT
                )
            except TimeoutError as e:
                raise MarketDataError(
                    f"Tapetide {name} timed out after {TAPETIDE_CALL_TIMEOUT}s"
                ) from e
            except MarketDataError:
                raise
            except Exception as e:  # httpx transport errors, MCPError, ValidationError
                raise MarketDataError(f"Tapetide {name} failed: {e}") from e
        if result.is_error:
            raise TapetideToolError(f"Tapetide {name} returned an error: {_error_text(result)}")
        return result.structured_content or {}

    async def _call_batch_quotes(self, symbols: list[str]) -> list[dict]:
        """Call the get_batch_quotes tool and return its `data` list."""
        payload = await self._call_tool("get_batch_quotes", {"symbols": symbols})
        return payload.get("data", [])
