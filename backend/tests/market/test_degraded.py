"""Tests for Tapetide degraded mode and the manager's simulator fallback (§6)."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.cache import PriceCache
from app.market.manager import MarketDataManager
from app.market.simulator import SimulatorDataSource
from app.market.tapetide_client import TapetideDataSource


def _failing_source(max_failures: int = 3) -> TapetideDataSource:
    source = TapetideDataSource(
        api_key="test-key", price_cache=PriceCache(), max_failures=max_failures
    )
    source._tickers = ["RELIANCE"]
    source._client = MagicMock()
    source._client.call_tool = AsyncMock(side_effect=Exception("network error"))
    return source


def _ok_client() -> MagicMock:
    client = MagicMock()
    result = MagicMock()
    result.is_error = False  # unset MagicMock attr is truthy -> would read as a tool error
    result.structured_content = {
        "data": [
            {
                "requested": "RELIANCE",
                "symbol": "RELIANCE",
                "price": 1.0,
                "prev_close": 1.0,
                "updated_at": "2026-10-16T10:00:00+00:00",
                "found": True,
            }
        ]
    }
    client.call_tool = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
class TestTapetideDegradedMode:
    async def test_degraded_after_n_consecutive_failures(self):
        source = _failing_source()
        for _ in range(2):
            await source._poll_once()
        assert not source.is_degraded()
        await source._poll_once()
        assert source.is_degraded()

    async def test_success_resets_failure_count(self):
        source = _failing_source()
        failing = source._client
        await source._poll_once()
        await source._poll_once()
        source._client = _ok_client()
        await source._poll_once()
        source._client = failing
        await source._poll_once()
        await source._poll_once()
        assert not source.is_degraded()

    async def test_multi_batch_failure_counts_once_per_poll(self):
        source = _failing_source()
        source._tickers = [f"TICK{i}" for i in range(25)]  # two batches
        await source._poll_once()
        assert source._consecutive_failures == 1

    async def test_dead_poll_task_is_degraded(self):
        source = TapetideDataSource(api_key="test-key", price_cache=PriceCache())

        async def crash():
            raise RuntimeError("poller crashed")

        source._task = asyncio.create_task(crash())
        await asyncio.sleep(0.01)
        assert source.is_degraded()

    async def test_stopped_source_is_not_degraded(self):
        source = TapetideDataSource(api_key="test-key", price_cache=PriceCache())
        await source.start([])
        await source.stop()
        assert not source.is_degraded()

    async def test_simulator_is_never_degraded(self):
        assert not SimulatorDataSource(price_cache=PriceCache()).is_degraded()


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _tapetide_manager(clock: _Clock) -> MarketDataManager:
    cache = PriceCache()
    manager = MarketDataManager(cache, check_interval=100.0, fallback_cooldown=300.0, clock=clock)
    manager._active = TapetideDataSource(api_key="test-key", price_cache=cache)
    manager._active._tickers = ["RELIANCE", "TCS"]
    return manager


async def _handover(manager: MarketDataManager) -> None:
    """Run one supervisor check while key + trading hours say 'Tapetide'."""
    with patch.dict(os.environ, {"TAPETIDE_API_KEY": "k"}, clear=True):
        with patch("app.market.factory.is_nse_trading_hours", return_value=True):
            await manager._maybe_handover()


@pytest.mark.asyncio
class TestDegradedFallback:
    async def test_degraded_tapetide_falls_back_to_simulator(self):
        manager = _tapetide_manager(_Clock())
        manager._active._consecutive_failures = 3
        await _handover(manager)
        assert isinstance(manager._active, SimulatorDataSource)
        assert set(manager.get_tickers()) == {"RELIANCE", "TCS"}
        assert manager._force_fallback
        await manager.stop()

    async def test_latch_prevents_swap_back_during_cooldown(self):
        clock = _Clock()
        manager = _tapetide_manager(clock)
        manager._active._consecutive_failures = 3
        await _handover(manager)
        clock.now += 299
        await _handover(manager)
        assert isinstance(manager._active, SimulatorDataSource)
        await manager.stop()

    async def test_retries_tapetide_after_cooldown(self):
        clock = _Clock()
        manager = _tapetide_manager(clock)
        manager._active._consecutive_failures = 3
        await _handover(manager)
        clock.now += 301
        await _handover(manager)
        assert isinstance(manager._active, TapetideDataSource)
        assert not manager._force_fallback
        await manager.stop()

    async def test_failure_after_retry_rearms_latch(self):
        clock = _Clock()
        manager = _tapetide_manager(clock)
        manager._active._consecutive_failures = 3
        await _handover(manager)
        clock.now += 301
        await _handover(manager)
        manager._active._consecutive_failures = 3
        await _handover(manager)
        assert isinstance(manager._active, SimulatorDataSource)
        assert manager._force_fallback
        assert manager._retry_after == clock.now + 300
        await manager.stop()

    async def test_healthy_tapetide_is_not_replaced(self):
        manager = _tapetide_manager(_Clock())
        await _handover(manager)
        assert isinstance(manager._active, TapetideDataSource)
        await manager.stop()
