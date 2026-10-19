"""Abstract interface for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataError(Exception):
    """Raised when a market data source cannot be reached — a transport or
    connection failure — as distinct from a definitive "symbol not found"
    answer. This lets the validation path (§6) map an unreachable source to a
    5xx ("couldn't check") rather than a 400 ("no such ticker"), so a network
    blip is never reported to the user as an invalid symbol.
    """


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it reads from the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])
        # ... app runs ...
        await source.add_ticker("TSLA")
        await source.remove_ticker("GOOGL")
        # ... app shutting down ...
        await source.stop()
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates for the given tickers.

        Starts a background task that periodically writes to the PriceCache.
        Must be called exactly once. Calling start() twice is undefined behavior.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task and release resources.

        Safe to call multiple times. After stop(), the source will not write
        to the cache again.
        """

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present.

        The next update cycle will include this ticker.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set. No-op if not present.

        Also removes the ticker from the PriceCache.
        """

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""

    def is_degraded(self) -> bool:
        """True if the source is persistently failing and should be replaced.

        Lets `MarketDataManager` fall back to the simulator (§6, "Tapetide
        Failure / Degraded Mode"). Sources that cannot fail (the simulator)
        keep this default of False.
        """
        return False

    @abstractmethod
    async def validate_ticker(self, ticker: str) -> bool:
        """Return True if `ticker` is a real, recognized symbol for this source.

        Used before adding a ticker to the watchlist, so an unrecognized
        symbol can be rejected with a user-facing error instead of silently
        never receiving a price.

        The bool answer means the source was actually reached and gave a
        verdict (True = exists, False = does not). If the source cannot be
        reached at all (transport/connection failure), this raises
        `MarketDataError` instead of returning False — the caller must not
        treat "couldn't check" as "invalid symbol" (§6). Sources with no
        network dependency (the simulator) never raise.
        """
