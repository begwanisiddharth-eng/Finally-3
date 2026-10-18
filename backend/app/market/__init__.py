"""Market data subsystem for FinAlly.

Public API:
    PriceUpdate         - Immutable price snapshot dataclass
    PriceCache          - Thread-safe in-memory price store
    MarketDataSource    - Abstract interface for data providers
    MarketDataManager   - Owns the active source and hands it over when the
                           desired source (Tapetide vs simulator) changes
                           mid-session. Downstream code (main.py) should use
                           this, not create_market_data_source directly.
    create_market_data_source - Factory that selects simulator or Tapetide
                                 for the *current* moment; used internally
                                 by MarketDataManager and in tests.
    create_stream_router - FastAPI router factory for SSE endpoint
"""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataError, MarketDataSource
from .manager import MarketDataManager
from .models import PriceUpdate
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "MarketDataError",
    "MarketDataManager",
    "create_market_data_source",
    "create_stream_router",
]
