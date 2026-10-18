"""Tests for TapetideDataSource (mocked MCP client)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.market.cache import PriceCache
from app.market.tapetide_client import TapetideDataSource


def _quote(requested: str, price: float, updated_at: str, found: bool = True) -> dict:
    return {
        "requested": requested,
        "symbol": requested,
        "price": price if found else None,
        "updated_at": updated_at if found else None,
        "found": found,
    }


def _mock_client(data: list[dict]) -> MagicMock:
    """Build a mock mcp.Client whose call_tool returns `data` as structured content."""
    client = MagicMock()
    result = MagicMock()
    result.structured_content = {"data": data, "meta": {"count": len(data)}}
    client.call_tool = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
class TestTapetideDataSource:
    """Unit tests for TapetideDataSource with a mocked MCP client."""

    async def test_poll_updates_cache(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["RELIANCE", "TCS"]
        source._client = _mock_client(
            [
                _quote("RELIANCE", 1211.20, "2026-10-16T10:29:44+00:00"),
                _quote("TCS", 2465.00, "2026-10-16T10:29:35+00:00"),
            ]
        )

        await source._poll_once()

        assert cache.get_price("RELIANCE") == 1211.20
        assert cache.get_price("TCS") == 2465.00

    async def test_unrecognized_ticker_not_cached(self):
        """A `found: false` quote is a validation signal, not an error — skip it."""
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["NOTAREALTICKER"]
        source._client = _mock_client([_quote("NOTAREALTICKER", 0, "", found=False)])

        await source._poll_once()

        assert cache.get_price("NOTAREALTICKER") is None

    async def test_uses_requested_not_symbol_as_cache_key(self):
        """A renamed/restructured symbol must still be cached under the ticker we asked for."""
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["TATAMOTORS"]
        quote = _quote("TATAMOTORS", 421.05, "2026-10-16T10:29:41+00:00")
        quote["symbol"] = "TMCV"  # Tapetide resolved a different current symbol
        source._client = _mock_client([quote])

        await source._poll_once()

        assert cache.get_price("TATAMOTORS") == 421.05
        assert cache.get_price("TMCV") is None

    async def test_malformed_quote_skipped(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["RELIANCE"]
        bad_quote = {"requested": "RELIANCE", "found": True}  # missing price/updated_at
        source._client = _mock_client([bad_quote])

        await source._poll_once()  # Should not raise

        assert cache.get_price("RELIANCE") is None

    async def test_api_error_does_not_crash(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["RELIANCE"]
        source._client = MagicMock()
        source._client.call_tool = AsyncMock(side_effect=Exception("network error"))

        await source._poll_once()  # Should not raise

        assert cache.get_price("RELIANCE") is None

    async def test_batches_over_20_symbols(self):
        """Calling get_batch_quotes with >20 symbols issues multiple calls."""
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = [f"TICK{i}" for i in range(25)]
        source._client = _mock_client([_quote("TICK0", 100.0, "2026-10-16T10:00:00+00:00")])

        await source._poll_once()

        assert source._client.call_tool.call_count == 2

    async def test_empty_tickers_skips_poll(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        source._tickers = []
        source._client = MagicMock()
        source._client.call_tool = AsyncMock()

        await source._poll_once()

        source._client.call_tool.assert_not_called()

    async def test_add_ticker_uppercase_and_strip(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("  reliance  ")

        assert "RELIANCE" in source.get_tickers()

    async def test_remove_ticker(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["RELIANCE", "TCS"]
        cache.update("RELIANCE", 1211.20)

        await source.remove_ticker("RELIANCE")

        assert "RELIANCE" not in source.get_tickers()
        assert cache.get("RELIANCE") is None

    async def test_get_tickers(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["RELIANCE", "TCS"]

        assert source.get_tickers() == ["RELIANCE", "TCS"]

    async def test_stop_is_idempotent(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)

        await source.stop()
        await source.stop()  # Should not raise

    async def test_validate_ticker_found(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        source._client = _mock_client([_quote("RELIANCE", 1211.20, "2026-10-16T10:29:44+00:00")])

        assert await source.validate_ticker("reliance") is True

    async def test_validate_ticker_not_found(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        source._client = _mock_client([_quote("NOTAREALTICKER", 0, "", found=False)])

        assert await source.validate_ticker("NOTAREALTICKER") is False

    async def test_validate_ticker_without_connection(self):
        cache = PriceCache()
        source = TapetideDataSource(api_key="test-key", price_cache=cache)
        # No client connected yet (start() not called)

        assert await source.validate_ticker("RELIANCE") is False
