# FinAlly Backend

FastAPI backend for the FinAlly AI Trading Workstation.

## Structure

- `app/` - Application code
  - `main.py` - FastAPI entrypoint: lifespan init/shutdown, manager wiring, static mount, error envelope
  - `db.py` - SQLite (aiosqlite) data-access layer, schema init, seeding, reset
  - `portfolio.py` - Trade execution, P&L, portfolio valuation
  - `watchlist.py` - Watchlist add/remove, 20-ticker cap, ticker validation
  - `chat.py` - LLM chat (LiteLLM -> Groq), structured outputs, auto-execution, mock mode
  - `schemas.py` - Pydantic request models
  - `routes/` - API routers: `portfolio.py`, `watchlist.py`, `chat.py`, `health.py`, `system.py` (reset)
  - `market/` - Market data subsystem
    - `models.py` - PriceUpdate dataclass
    - `cache.py` - Thread-safe price cache
    - `interface.py` - MarketDataSource abstract interface
    - `simulator.py` - GBM-based market simulator
    - `tapetide_client.py` - Tapetide MCP client for real NSE data
    - `nse_hours.py` - NSE trading-hours check
    - `factory.py` - Data source factory
    - `manager.py` - MarketDataManager: owns the active source, live handover, degraded/stale fallback
    - `stream.py` - SSE streaming endpoint
    - `seed_prices.py` - Default ticker prices, parameters, and the curated NSE symbol universe

- `tests/` - Unit and integration tests (151 passing)
  - `market/` - Market data tests
  - `test_api.py` - API integration tests via FastAPI TestClient

## Running Tests

```bash
# Install dependencies
uv sync --extra dev

# Run all tests
uv run --extra dev pytest

# Run with coverage
uv run --extra dev pytest --cov=app --cov-report=html

# Run specific test file
uv run --extra dev pytest tests/market/test_simulator.py

# Run the terminal demo (rich is an optional 'demo' extra, not an app dependency)
uv run --extra demo market_data_demo.py

# Run with verbose output
uv run pytest -v
```

## Environment Variables

- `TAPETIDE_API_KEY` - Optional. If set, and it is currently NSE trading hours, use real NSE market data from Tapetide MCP. Otherwise, use the built-in simulator.

## Development

```bash
# Install dependencies
uv sync --extra dev

# Run linter
uv run ruff check .

# Format code
uv run ruff format .
```
