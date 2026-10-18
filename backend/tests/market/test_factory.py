"""Tests for market data source factory."""

import os
from unittest.mock import patch

from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.simulator import SimulatorDataSource
from app.market.tapetide_client import TapetideDataSource


class TestFactory:
    """Tests for create_market_data_source factory."""

    def test_creates_simulator_when_no_api_key(self):
        """Test that simulator is created when TAPETIDE_API_KEY is not set."""
        cache = PriceCache()

        with patch.dict(os.environ, {}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_empty(self):
        """Test that simulator is created when TAPETIDE_API_KEY is empty."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": ""}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_whitespace(self):
        """Test that simulator is created when TAPETIDE_API_KEY is whitespace."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "   "}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_set_but_outside_trading_hours(self):
        """Test that simulator is used outside NSE trading hours even with a key set."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=False):
                source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_tapetide_when_api_key_set_and_trading_hours(self):
        """Test that Tapetide client is created during NSE trading hours with a key set."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                source = create_market_data_source(cache)

        assert isinstance(source, TapetideDataSource)

    def test_tapetide_receives_api_key(self):
        """Test that Tapetide client receives the API key."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key-123"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                source = create_market_data_source(cache)

        assert isinstance(source, TapetideDataSource)
        assert source._api_key == "test-key-123"

    def test_simulator_receives_cache(self):
        """Test that simulator receives the cache reference."""
        cache = PriceCache()

        with patch.dict(os.environ, {}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)
        assert source._cache is cache

    def test_tapetide_receives_cache(self):
        """Test that Tapetide client receives the cache reference."""
        cache = PriceCache()

        with patch.dict(os.environ, {"TAPETIDE_API_KEY": "test-key"}, clear=True):
            with patch("app.market.factory.is_nse_trading_hours", return_value=True):
                source = create_market_data_source(cache)

        assert isinstance(source, TapetideDataSource)
        assert source._cache is cache
