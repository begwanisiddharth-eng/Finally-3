"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .nse_hours import is_nse_trading_hours
from .simulator import SimulatorDataSource
from .tapetide_client import TapetideDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - TAPETIDE_API_KEY set and non-empty, AND it is currently NSE trading
      hours (9:15am-3:30pm IST, Mon-Fri) → TapetideDataSource (real data)
    - Otherwise → SimulatorDataSource (GBM simulation)

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    api_key = os.environ.get("TAPETIDE_API_KEY", "").strip()

    if api_key and is_nse_trading_hours():
        logger.info("Market data source: Tapetide MCP (real NSE data)")
        return TapetideDataSource(api_key=api_key, price_cache=price_cache)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
