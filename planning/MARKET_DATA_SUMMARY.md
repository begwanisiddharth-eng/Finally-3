# Market Data Backend — Summary

**Status:** Complete, tested, reviewed, all issues resolved. Rewritten 2026-10-18 to replace the
original Massive/Polygon.io (US-ticker) implementation with Tapetide MCP (NSE-ticker), per the
plan's finalized datasource decision.

## What Was Built

A complete market data subsystem in `backend/app/market/` (9 modules) providing live price
simulation and real NSE market data via a unified interface.

### Architecture

```
MarketDataSource (ABC)
├── SimulatorDataSource   →  GBM simulator (default, no API key needed)
└── TapetideDataSource    →  Tapetide MCP poller (when TAPETIDE_API_KEY set
                               AND it is NSE trading hours)
        │
        ▼
   PriceCache (thread-safe, in-memory)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

### Modules

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate` — immutable frozen dataclass (ticker, price, previous_price, timestamp, change, direction) |
| `interface.py` | `MarketDataSource` — abstract base class defining `start/stop/add_ticker/remove_ticker/get_tickers/validate_ticker` |
| `cache.py` | `PriceCache` — thread-safe price store with version counter for SSE change detection |
| `seed_prices.py` | Realistic NSE seed prices, per-ticker GBM params (drift/volatility), sector correlation groups, and the curated `NSE_SYMBOL_UNIVERSE` used to validate watchlist additions on the simulator |
| `nse_hours.py` | `is_nse_trading_hours()` — IST weekday/clock-time gate (no holiday calendar) |
| `simulator.py` | `GBMSimulator` (Geometric Brownian Motion with Cholesky-correlated moves) + `SimulatorDataSource` |
| `tapetide_client.py` | `TapetideDataSource` — MCP streamable-HTTP client polling Tapetide's `get_batch_quotes` tool |
| `factory.py` | `create_market_data_source()` — selects simulator or Tapetide based on `TAPETIDE_API_KEY` + trading hours |
| `stream.py` | `create_stream_router()` — FastAPI SSE endpoint factory using version-based change detection |

### Key Design Decisions

- **Strategy pattern** — both data sources implement the same ABC; downstream code is source-agnostic
- **PriceCache as single point of truth** — producers write, consumers read; no direct coupling
- **GBM with correlated moves** — Cholesky decomposition of a sector-based correlation matrix (banking, IT, auto groups correlate at 0.6; cross-sector/unknown tickers at 0.3)
- **Random shock events** — ~0.1% chance per tick per ticker of a 2-5% move for visual drama
- **SSE over WebSockets** — simpler, one-way push, universal browser support
- **Ticker validation** — Tapetide's `get_batch_quotes` returns `found: false` for an unrecognized symbol, which is used directly as the validation signal when Tapetide is active; the simulator validates against the static `NSE_SYMBOL_UNIVERSE` list instead, since it has no real backing universe of its own
- **Cache key is the requested ticker, not Tapetide's resolved symbol** — a corporate action (e.g. TATAMOTORS → TMCV) can make Tapetide return a different current symbol than the one requested; the cache is always keyed by what the watchlist asked for
- **Simulator reseeds from the last real price when available** — if the cache already holds a Tapetide-sourced price for a ticker (e.g. trading hours just ended), the simulator starts from that price instead of the static seed table

## Test Suite

7 test modules in `backend/tests/market/`.

| Module | Covers |
|--------|--------|
| test_models.py | `models.py` |
| test_cache.py | `cache.py` |
| test_simulator.py | `GBMSimulator` math, sector correlation, seeding |
| test_simulator_source.py | `SimulatorDataSource` integration |
| test_tapetide.py | `TapetideDataSource` (mocked MCP client): polling, batching over 20 symbols, unrecognized-ticker handling, requested-vs-resolved-symbol cache keying, validation |
| test_factory.py | Source selection by API key presence + trading hours |
| test_nse_hours.py | `is_nse_trading_hours()` boundaries, weekends, timezone conversion |

## Demo

A Rich terminal demo is available at `backend/market_data_demo.py`:

```bash
cd backend
uv run market_data_demo.py
```

Displays a live-updating dashboard with the 10 default NSE tickers, sparklines, color-coded
direction arrows, and an event log for notable price moves. Runs 60 seconds or until Ctrl+C.
Always runs against the simulator (not Tapetide).

## Usage for Downstream Code

```python
from app.market import PriceCache, create_market_data_source

# Startup
cache = PriceCache()
source = create_market_data_source(cache)  # Reads TAPETIDE_API_KEY + trading hours
await source.start(["HDFCBANK", "INFY", "RELIANCE", ...])

# Read prices
update = cache.get("HDFCBANK")      # PriceUpdate or None
price = cache.get_price("HDFCBANK") # float or None
all_prices = cache.get_all()        # dict[str, PriceUpdate]

# Dynamic watchlist (validate before adding)
if await source.validate_ticker("WIPRO"):
    await source.add_ticker("WIPRO")
await source.remove_ticker("TCS")

# Shutdown
await source.stop()
```
