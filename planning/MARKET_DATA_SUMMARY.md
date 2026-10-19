# Market Data Backend — Summary

**Status:** Complete, tested, reviewed, all issues resolved. Rewritten 2026-10-18 to replace the
original Massive/Polygon.io (US-ticker) implementation with Tapetide MCP (NSE-ticker); extended
2026-10-19 with live Tapetide↔simulator handover (`MarketDataManager`) and day-change tracking,
per the plan's finalized decisions.

## What Was Built

A complete market data subsystem in `backend/app/market/` (10 modules) providing live price
simulation and real NSE market data via a unified interface, with automatic handover between
sources as NSE trading hours start/end mid-session.

### Architecture

```
MarketDataManager (owns the active source, supervises handover)
        │
        ├── creates via create_market_data_source() ──┬── SimulatorDataSource
        │                                              └── TapetideDataSource
        ▼
   PriceCache (thread-safe, in-memory — never replaced across a handover)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

### Modules

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate` — immutable frozen dataclass (ticker, price, previous_price, previous_close, timestamp; properties change/change_percent, day_change/day_change_percent, direction) |
| `interface.py` | `MarketDataSource` — abstract base class defining `start/stop/add_ticker/remove_ticker/get_tickers/validate_ticker` |
| `cache.py` | `PriceCache` — thread-safe price store with version counter for SSE change detection |
| `seed_prices.py` | Realistic NSE seed prices, per-ticker GBM params (drift/volatility), sector correlation groups, and the curated `NSE_SYMBOL_UNIVERSE` used to validate watchlist additions on the simulator |
| `nse_hours.py` | `is_nse_trading_hours()` — IST weekday/clock-time gate (no holiday calendar) |
| `simulator.py` | `GBMSimulator` (Geometric Brownian Motion with Cholesky-correlated moves) + `SimulatorDataSource` |
| `tapetide_client.py` | `TapetideDataSource` — MCP streamable-HTTP client polling Tapetide's `get_batch_quotes` tool |
| `factory.py` | `create_market_data_source()` — builds a single source for the *current* moment, based on `TAPETIDE_API_KEY` + trading hours |
| `manager.py` | `MarketDataManager` — owns the active source for the app's lifetime; a background supervisor task re-evaluates every 60s and hands over to the other source when the desired one changes (market open/close, key added/removed), without replacing the shared cache |
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
- **Live handover, not a startup-only choice** — `MarketDataManager` re-evaluates the desired source every 60s and swaps when it changes, rather than deciding once and running that choice forever. The shared `PriceCache` is never replaced, so SSE clients see no interruption; the new source inherits the old one's ticker list and (on a Tapetide→simulator handover) the last real prices already sitting in the cache
- **Day-change baseline is distinct from tick-over-tick** — `previous_close` (real exchange close under Tapetide; session-start price under the simulator, which has no real "yesterday") drives `day_change`/`day_change_percent`, separate from `previous_price`, which drives the per-tick flash

## Test Suite

10 test modules in `backend/tests/market/` (125 tests).

| Module | Covers |
|--------|--------|
| test_models.py | `models.py`, including day-change vs tick-over-tick fields |
| test_cache.py | `cache.py`, including `previous_close` carry-forward/override |
| test_simulator.py | `GBMSimulator` math, sector correlation, seeding |
| test_simulator_source.py | `SimulatorDataSource` integration |
| test_tapetide.py | `TapetideDataSource` (mocked MCP client): polling, batching over 20 symbols, unrecognized-ticker handling, requested-vs-resolved-symbol cache keying, `prev_close` passthrough, validation, `is_error` tool-error handling, per-call timeout, mid-poll removal guard |
| test_degraded.py | Degraded mode: N consecutive failures and dead-task detection, manager fallback to the simulator, cooldown latch (suppress flap, retry after cooldown, re-arm) |
| test_factory.py | Source selection by API key presence + trading hours |
| test_nse_hours.py | `is_nse_trading_hours()` boundaries, weekends, timezone conversion |
| test_manager.py | `MarketDataManager`: handover in both directions, ticker-list preservation across handover, seeding from cached real price, no-op when the desired source is unchanged, supervisor loop triggers handover |
| test_stream.py | `create_stream_router` returns an independent router per call (one `/prices` route each) |

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
from app.market import PriceCache, MarketDataManager

# Startup — use the manager, not create_market_data_source() directly, so
# handovers between Tapetide and the simulator happen automatically.
cache = PriceCache()
manager = MarketDataManager(cache)  # Reads TAPETIDE_API_KEY + trading hours internally
await manager.start(["HDFCBANK", "INFY", "RELIANCE", ...])

# Read prices
update = cache.get("HDFCBANK")      # PriceUpdate or None
price = cache.get_price("HDFCBANK") # float or None
all_prices = cache.get_all()        # dict[str, PriceUpdate]

# Dynamic watchlist (validate before adding). A successful validate_ticker
# also seeds the cache (Tapetide writes the quote it fetched; the simulator
# seeds on add_ticker), so an immediate trade on the new ticker has a price.
if await manager.validate_ticker("WIPRO"):
    await manager.add_ticker("WIPRO")
await manager.remove_ticker("TCS")

# Shutdown
await manager.stop()
```
