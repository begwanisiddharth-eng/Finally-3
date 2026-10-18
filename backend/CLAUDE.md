# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, MarketDataManager
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `previous_close`, `timestamp`, plus properties `change`/`change_percent` (tick-over-tick, drives the flash), `day_change`/`day_change_percent` (session/day baseline, drives the watchlist's daily change %), `direction` ("up"/"down"/"flat"), and `to_dict()` for JSON serialization.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None, previous_close=None) -> PriceUpdate`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)`
  - `version` property — monotonic counter, increments on every update (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource`, `TapetideDataSource`, and `MarketDataManager`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`. Also exposes `validate_ticker(ticker) -> bool`.

- **`MarketDataManager(price_cache, check_interval=60.0)`** — **Use this, not `create_market_data_source`, for anything long-running (i.e. `app/main.py`).** Owns the active source and re-checks every `check_interval` seconds whether the desired source (Tapetide vs simulator, per `TAPETIDE_API_KEY` + NSE trading hours) has changed; if so, it starts the new source with the same ticker list, stops the old one, and swaps — the shared `PriceCache` is never replaced, so this is transparent to SSE clients. Also exposes `active_source_name` (e.g. for a health-check field).

- **`create_market_data_source(cache)`** — Factory returning a single, unstarted source for the *current* moment (Tapetide if `TAPETIDE_API_KEY` is set AND it is currently NSE trading hours — see `nse_hours.is_nse_trading_hours` — otherwise the simulator). Used internally by `MarketDataManager` and directly in tests; application code should go through the manager so handovers happen automatically.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
```

### Seed Data

Default tickers (NSE): HEROMOTOCO, BEL, PIDILITIND, LTF, HDFCBANK, INFY, RELIANCE, TCS, ICICIBANK, TATAMOTORS. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`, which also holds `NSE_SYMBOL_UNIVERSE`, the curated symbol list the simulator validates watchlist additions against.

## Running Tests

```bash
uv run --extra dev pytest -v              # All tests
uv run --extra dev pytest --cov=app       # With coverage
uv run --extra dev ruff check app/ tests/ # Lint
```

## Demo

```bash
uv run --extra demo market_data_demo.py   # Live terminal dashboard with simulated prices
```
