# FinAlly - AI Trading Workstation

An AI-powered trading workstation that streams live market data, simulates portfolio trading with
Rs 10 lakh of virtual cash, and includes an LLM chat assistant that can analyze positions and
execute trades via natural language. It looks and feels like a modern Bloomberg-style terminal with
an AI copilot.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Status

The platform is **feature-complete** and runs end to end on a single port (no Docker):

- **Backend** — market data subsystem (GBM simulator, Tapetide MCP client, live handover + degraded
  and stale-feed fallback), SQLite database, all REST + SSE endpoints, LLM chat with auto-execution,
  start/stop scripts. 151 backend/API tests passing.
- **Frontend** — Next.js static export (React 19, TypeScript strict, Tailwind v4, Lightweight
  Charts v5), served by FastAPI. 12 Vitest/RTL unit tests passing.
- **E2E** — Playwright suite in `test/`, 7 key scenarios passing.

See [`planning/STATUS.md`](planning/STATUS.md) for the authoritative build status and
[`planning/PLAN.md`](planning/PLAN.md) for the full technical specification.

## Quick Start

```bash
./scripts/start_mac.sh        # macOS/Linux
.\scripts\start_windows.ps1   # Windows (PowerShell)
```

The script creates `.env` from `.env.example` if missing (set `GROQ_API_KEY` in it, or set
`LLM_MOCK=true`), builds the frontend, starts the backend, and opens http://127.0.0.1:8000. Use
`scripts/stop_mac.sh` / `scripts/stop_windows.ps1` to stop; the database persists across runs. Pass
`--build` to force a frontend rebuild.

No login, no signup — on first launch you get the default 10-ticker watchlist, Rs 10,00,000 in
virtual cash, and a live simulated market.

## Using FinAlly

- **Header** — shows **Cash**, **Equity** (value of your holdings) and **Total Value**, all updating
  live; a data-source badge (**SIMULATED** or **LIVE (NSE)**), a connection dot, and a data-freshness
  indicator. A prominent red **Reset** button (top-right) returns everything to a first-launch state
  after a confirmation dialog (default watchlist, no positions, Rs 10 lakh cash, blank chat).
- **Watchlist** — your tracked tickers with live price, day change %, and a sparkline. Add a ticker
  in the box (max 20); click the **×** to remove one. Click any row to load it in the main chart.
- **Trade bar** — pick a symbol from the dropdown (your watchlist plus any held-but-unwatched
  position), enter a quantity (fractional allowed), and hit **Buy** or **Sell**. Market orders fill
  instantly at the current price. The quantity clears when you pick a new ticker.
- **Main chart** — a live, since-page-load price chart for the selected ticker, with an IST HH:MM
  time axis. It fills the available space so the panels below always stay visible.
- **Portfolio Value** — total portfolio value (cash + positions) over the last 60 minutes, as a
  clean line sampled from 30-second snapshots.
- **Portfolio Heatmap** — a treemap of your positions that fills the panel; each tile is sized by
  position weight and tinted green/red by profit/loss.
- **Positions** / **Recent Trades** — your holdings (ticker, qty, avg cost, price, P&L, %) and the
  latest trades. Each shows about five rows and scrolls for the rest.
- **AI Assistant** — chat in plain English: "buy 10 HDFCBANK", "sell half my INFY", "add WIPRO to
  my watchlist", or "how is my portfolio doing?" The assistant executes trades and watchlist changes
  automatically (simulated money, so no confirmation gate) and the panels update in step. Chat starts
  blank on each app launch.

## API

With the backend running, these endpoints are live (see [`planning/PLAN.md`](planning/PLAN.md) §8
for exact shapes):

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Status, active data source, feed freshness |
| GET | `/api/stream/prices` | SSE stream of live prices |
| GET | `/api/portfolio` | Cash, positions, valuation |
| POST | `/api/portfolio/trade` | Execute a market order |
| GET | `/api/portfolio/history` | Portfolio value snapshots |
| GET | `/api/portfolio/trades` | Trade log (most recent first) |
| GET/POST | `/api/watchlist` | List / add a ticker (max 20) |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |
| POST | `/api/chat` | Chat with the AI (auto-executes trades) |
| GET | `/api/chat/history` | Last 20 chat messages |
| POST | `/api/reset` | Reset to a first-launch state |

## Backend Development

```bash
cd backend
uv sync --extra dev
uv run --extra dev pytest          # 151 tests
uv run --extra dev ruff check app/ tests/
uv run --extra demo market_data_demo.py
```

See [`backend/README.md`](backend/README.md) for the market data API. Frontend unit tests:
`cd frontend && npm test`. E2E: see [`test/README.md`](test/README.md).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes, unless `LLM_MOCK=true` | Groq API key for AI chat |
| `TAPETIDE_API_KEY` | No | Tapetide MCP bearer token for real NSE data; omit to use the simulator |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses (testing) |
| `MARKET_DATA_SOURCE` | No | `auto` (default), `simulator`, or `tapetide` |
| `DATABASE_PATH` | No | SQLite file location (default: `db/finally.db`) |
| `FRONTEND_DIR` | No | Static export location (default: `frontend/out`) |
| `PORT` | No | Port the start scripts bind (default 8000); not read by the app |

Tapetide is capped at 400 calls/day, about 13 minutes of continuous polling, so use it for short
demo sessions. Outside NSE trading hours (or on a market holiday), FinAlly automatically runs the
simulator.

## Project Structure

```
frontend/    Next.js static export (built)
backend/     FastAPI uv project (built)
  app/       API routes, db, portfolio, chat, market data
  db/        schema.sql
  tests/     backend + API tests
planning/    Plan, status, and agent contracts (start with PLAN.md)
scripts/     Start/stop helpers
test/        Playwright E2E tests
db/          SQLite file at runtime
```

## License

See [LICENSE](LICENSE).
