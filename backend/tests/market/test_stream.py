"""Tests for the SSE streaming router factory."""

from app.market.cache import PriceCache
from app.market.stream import create_stream_router


def test_router_factory_is_independent():
    """Each create_stream_router() call returns a router with exactly one /prices
    route, rather than double-registering on a shared module-level router."""
    r1 = create_stream_router(PriceCache())
    r2 = create_stream_router(PriceCache())
    assert [r.path for r in r1.routes] == ["/api/stream/prices"]
    assert [r.path for r in r2.routes] == ["/api/stream/prices"]
