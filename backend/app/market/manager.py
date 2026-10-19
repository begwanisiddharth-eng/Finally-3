"""Supervises the active market data source and hands it over when the
desired source (Tapetide vs simulator) changes mid-session."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL = 60.0  # seconds between handover checks
HEALTH_CHECK_INTERVAL = 5.0  # a degraded source is noticed at least this often
DEFAULT_FALLBACK_COOLDOWN = 300.0  # seconds before retrying Tapetide after a fallback


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
        fallback_cooldown: float = DEFAULT_FALLBACK_COOLDOWN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache = price_cache
        self._check_interval = check_interval
        self._fallback_cooldown = fallback_cooldown
        self._clock = clock
        # Cooldown latch (§6): set when a degraded source forces a fallback so
        # the supervisor does not swap straight back to the still-broken one.
        self._force_fallback = False
        self._retry_after = 0.0
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

    # Stable lowercase labels for the active source. Consumed by the LLM
    # portfolio context (§9, drives the SEBI-disclaimer rule) and the
    # /api/health payload, so these must match the literals the plan uses --
    # not the Python class names.
    _SOURCE_LABELS = {
        "TapetideDataSource": "tapetide",
        "SimulatorDataSource": "simulator",
    }

    @property
    def active_source_name(self) -> str:
        """Stable label of the active source: 'tapetide', 'simulator', or 'none'."""
        if self._active is None:
            return "none"
        name = type(self._active).__name__
        return self._SOURCE_LABELS.get(name, name)

    # --- Internal ---

    async def _supervise(self) -> None:
        """Periodically check whether the desired source has changed."""
        while True:
            # Wake often enough to notice a degraded source promptly; the
            # desired-source check is cheap (env + clock), so run it each tick.
            await asyncio.sleep(min(self._check_interval, HEALTH_CHECK_INTERVAL))
            try:
                await self._maybe_handover()
            except Exception:
                logger.exception("Market data handover check failed")

    async def _maybe_handover(self) -> None:
        """Swap the active source if it is degraded or the desired source changed."""
        async with self._lock:
            if self._active is None:
                return

            if self._active.is_degraded() and not isinstance(self._active, SimulatorDataSource):
                self._force_fallback = True
                self._retry_after = self._clock() + self._fallback_cooldown
                logger.warning(
                    "%s is degraded; falling back to simulator for %.0fs",
                    type(self._active).__name__,
                    self._fallback_cooldown,
                )
                candidate: MarketDataSource = SimulatorDataSource(price_cache=self._cache)
            else:
                candidate = create_market_data_source(self._cache)
                if type(candidate) is type(self._active):
                    return  # No change in desired source.
                if self._force_fallback:
                    if self._clock() < self._retry_after:
                        return  # Latch holds: don't flap back to the broken source.
                    self._force_fallback = False  # Cooldown over: one fresh attempt.

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
