"""Supervises the active market data source and hands it over when the
desired source (Tapetide vs simulator) changes mid-session."""

from __future__ import annotations

import asyncio
import logging

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL = 60.0  # seconds between handover checks


class MarketDataManager(MarketDataSource):
    """Owns the active MarketDataSource and swaps it when the desired source
    changes (crossing an NSE trading-hours boundary, or TAPETIDE_API_KEY
    being set/unset), rather than deciding once at process startup.

    Downstream code (API routes, SSE streaming) depends only on this manager
    and the shared PriceCache, never on a concrete source directly, so a
    handover is transparent: the cache is never replaced, so in-flight SSE
    clients see no interruption. The new source inherits the current ticker
    list from the old one, and (via SimulatorDataSource's own seeding logic)
    picks up the last real price already sitting in the cache when handing
    over from Tapetide to the simulator.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
    ) -> None:
        self._cache = price_cache
        self._check_interval = check_interval
        self._active: MarketDataSource | None = None
        self._lock = asyncio.Lock()
        self._supervisor_task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        async with self._lock:
            self._active = create_market_data_source(self._cache)
            await self._active.start(tickers)
        self._supervisor_task = asyncio.create_task(
            self._supervise(), name="market-data-handover-supervisor"
        )
        logger.info("MarketDataManager started with source %s", type(self._active).__name__)

    async def stop(self) -> None:
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
        self._supervisor_task = None
        async with self._lock:
            if self._active:
                await self._active.stop()
                self._active = None

    async def add_ticker(self, ticker: str) -> None:
        async with self._lock:
            if self._active:
                await self._active.add_ticker(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        async with self._lock:
            if self._active:
                await self._active.remove_ticker(ticker)

    def get_tickers(self) -> list[str]:
        return self._active.get_tickers() if self._active else []

    async def validate_ticker(self, ticker: str) -> bool:
        async with self._lock:
            return await self._active.validate_ticker(ticker) if self._active else False

    @property
    def active_source_name(self) -> str:
        """Class name of the currently active source (e.g. for a /api/health field)."""
        return type(self._active).__name__ if self._active else "none"

    # --- Internal ---

    async def _supervise(self) -> None:
        """Periodically check whether the desired source has changed."""
        while True:
            await asyncio.sleep(self._check_interval)
            try:
                await self._maybe_handover()
            except Exception:
                logger.exception("Market data handover check failed")

    async def _maybe_handover(self) -> None:
        """Swap the active source if the env/trading-hours decision changed."""
        candidate = create_market_data_source(self._cache)

        async with self._lock:
            if self._active is None or type(candidate) is type(self._active):
                return  # No change in desired source.

            old = self._active
            tickers = old.get_tickers()
            await candidate.start(tickers)
            await old.stop()
            self._active = candidate
            logger.info(
                "Market data handover: %s -> %s (%d tickers)",
                type(old).__name__,
                type(candidate).__name__,
                len(tickers),
            )
