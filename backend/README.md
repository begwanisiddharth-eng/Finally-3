# FinAlly Backend

FastAPI backend for the FinAlly AI Trading Workstation.

## Structure

- `app/` - Application code
  - `market/` - Market data subsystem
    - `models.py` - PriceUpdate dataclass
    - `cache.py` - Thread-safe price cache
    - `interface.py` - MarketDataSource abstract interface
    - `simulator.py` - GBM-based market simulator
    - `tapetide_client.py` - Tapetide MCP client for real NSE data
    - `nse_hours.py` - NSE trading-hours check
    - `factory.py` - Data source factory
    - `stream.py` - SSE streaming endpoint
    - `seed_prices.py` - Default ticker prices, parameters, and the curated NSE symbol universe

- `tests/` - Unit and integration tests
  - `market/` - Market data tests

## Running Tests

```bash
# Install dependencies
uv sync --extra dev

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run specific test file
uv run pytest tests/market/test_simulator.py

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
