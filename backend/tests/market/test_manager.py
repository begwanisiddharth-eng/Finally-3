"""Tests for MarketDataManager (handover supervision)."""

import os
from unittest.mock import patch

import pytest

from app.market.cache import PriceCache
from app.market.manager import MarketDataManager
from app.market.simulator import SimulatorDataSource
from app.market.tapetide_client import TapetideDataSource


@pytest.mark.asyncio
class TestMarketDataManager:
    """Unit tests for MarketDataManager."""

    async def test_start_creates_source_from_current_env(self):
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])

        assert isinstance(manager._active, SimulatorDataSource)
        assert manager.active_source_name == "simulator"
        await manager.stop()

    async def test_active_source_name_uses_stable_labels(self):
        """active_source_name returns the plan's literals, not class names.

        The LLM portfolio context and /api/health both compare against
        'tapetide'/'simulator', so the mapping is a contract.
        """
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)
        assert manager.active_source_name == "none"

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])
        assert manager.active_source_name == "simulator"

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                await manager._maybe_handover()
        assert manager.active_source_name == "tapetide"
        await manager.stop()

    async def test_stop_is_idempotent(self):
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])

        await manager.stop()
        await manager.stop()  # Should not raise

    async def test_get_tickers_before_start_is_empty(self):
        cache = PriceCache()
        manager = MarketDataManager(cache)
        assert manager.get_tickers() == []

    async def test_validate_ticker_before_start_is_false(self):
        cache = PriceCache()
        manager = MarketDataManager(cache)
        assert await manager.validate_ticker("RELIANCE") is False

    async def test_add_and_remove_ticker_forwards_to_active_source(self):
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])

        await manager.add_ticker("TCS")
        assert "TCS" in manager.get_tickers()

        await manager.remove_ticker("TCS")
        assert "TCS" not in manager.get_tickers()

        await manager.stop()

    async def test_handover_simulator_to_tapetide(self):
        """When the env changes to favor Tapetide, the next check swaps sources."""
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])
        assert isinstance(manager._active, SimulatorDataSource)

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                await manager._maybe_handover()

        assert isinstance(manager._active, TapetideDataSource)
        await manager.stop()

    async def test_handover_tapetide_to_simulator_preserves_tickers(self):
        """Handing over keeps tracking the same tickers under the new source."""
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                await manager.start(["RELIANCE", "TCS"])
        assert isinstance(manager._active, TapetideDataSource)

        with patch.dict(os.environ, {}, clear=True):
            await manager._maybe_handover()

        assert isinstance(manager._active, SimulatorDataSource)
        assert set(manager.get_tickers()) == {"RELIANCE", "TCS"}
        await manager.stop()

    async def test_handover_seeds_simulator_from_last_real_price(self):
        """Switching Tapetide -> simulator mid-session inherits the cached real price."""
        cache = PriceCache()
        cache.update("RELIANCE", 1211.20)  # Simulate a real price already in the cache
        manager = MarketDataManager(cache, check_interval=100.0)
        manager._active = TapetideDataSource(api_key="test-key", price_cache=cache)
        manager._active._tickers = ["RELIANCE"]

        with patch.dict(os.environ, {}, clear=True):
            await manager._maybe_handover()

        assert isinstance(manager._active, SimulatorDataSource)
        assert cache.get_price("RELIANCE") == 1211.20
        await manager.stop()

    async def test_no_handover_when_source_type_unchanged(self):
        """No swap happens if the candidate source type matches the active one."""
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=100.0)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])
        original_source = manager._active

        with patch.dict(os.environ, {}, clear=True):
            await manager._maybe_handover()

        assert manager._active is original_source  # Unchanged, not swapped
        await manager.stop()

    async def test_supervise_triggers_handover_on_interval(self):
        """The background supervisor loop calls _maybe_handover on each tick."""
        cache = PriceCache()
        manager = MarketDataManager(cache, check_interval=0.05)

        with patch.dict(os.environ, {}, clear=True):
            await manager.start(["RELIANCE"])

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                import asyncio

                await asyncio.sleep(0.15)  # Let the supervisor tick at least once

        assert isinstance(manager._active, TapetideDataSource)
        await manager.stop()
