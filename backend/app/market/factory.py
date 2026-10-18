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

    `MARKET_DATA_SOURCE` (default `auto`) is an explicit override, mainly for
    tests and demos so source selection does not depend on the wall clock:

    - `simulator` → always SimulatorDataSource (disables handover to Tapetide)
    - `tapetide`  → always TapetideDataSource (requires TAPETIDE_API_KEY)
    - `auto`      → TAPETIDE_API_KEY set and non-empty AND currently NSE trading
      hours (9:15am-3:30pm IST, Mon-Fri) → TapetideDataSource; otherwise
      SimulatorDataSource

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    override = os.environ.get("MARKET_DATA_SOURCE", "auto").strip().lower()
    api_key = os.environ.get("TAPETIDE_API_KEY", "").strip()

    if override == "simulator":
        logger.info("Market data source: GBM Simulator (forced by MARKET_DATA_SOURCE)")
        return SimulatorDataSource(price_cache=price_cache)
    if override == "tapetide":
        if not api_key:
            raise RuntimeError("MARKET_DATA_SOURCE=tapetide requires TAPETIDE_API_KEY to be set")
        logger.info("Market data source: Tapetide MCP (forced by MARKET_DATA_SOURCE)")
        return TapetideDataSource(api_key=api_key, price_cache=price_cache)

    if api_key and is_nse_trading_hours():
        logger.info("Market data source: Tapetide MCP (real NSE data)")
        return TapetideDataSource(api_key=api_key, price_cache=price_cache)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
