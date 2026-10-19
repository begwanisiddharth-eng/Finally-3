# FinAlly - AI Trading Workstation

An AI-powered trading workstation that streams live market data, simulates portfolio trading with Rs 10 lakh of virtual cash, and includes an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Status

See [`planning/STATUS.md`](planning/STATUS.md) for the authoritative build status.

- **Done**: the full backend - market data subsystem (simulator, Tapetide client, live handover), SQLite database, all REST + SSE API endpoints, LLM chat with auto-execution, start/stop scripts, and 144 passing backend tests.
- **To build**: the Next.js frontend and the Playwright E2E suite in `test/`.

The backend runs today and serves every `/api/*` endpoint. Until the frontend is built, the start scripts launch the API only.

## Architecture

Single local process serving everything on one port, no Docker:

- **Frontend**: Next.js (static export), TypeScript, Tailwind CSS (to build)
- **Backend**: FastAPI (Python, managed with `uv`), SSE streaming
- **Database**: SQLite (`db/finally.db`), initialized and seeded at startup
- **AI**: LiteLLM -> Groq (`groq/openai/gpt-oss-120b`) with structured outputs
- **Market data**: built-in GBM simulator by default; real NSE data via the Tapetide MCP server during trading hours if `TAPETIDE_API_KEY` is set

## Prerequisites

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js LTS and npm (only needed once the frontend exists)
- Windows only: the `.ps1` scripts may need `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Quick Start

```bash
./scripts/start_mac.sh        # macOS/Linux
.\scripts\start_windows.ps1   # Windows (PowerShell)
```

The script creates `.env` from `.env.example` if missing (set `GROQ_API_KEY` in it, or set `LLM_MOCK=true`), builds the frontend if present, starts the backend, and prints the URL: http://127.0.0.1:8000. Use `scripts/stop_mac.sh` or `scripts/stop_windows.ps1` to stop; the database persists across runs. Pass `--build` to force a frontend rebuild.

## API

With the backend running, the following endpoints are live (see PLAN.md section 8 for shapes):

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Status, active data source, feed freshness |
| GET | `/api/stream/prices` | SSE stream of live prices |
| GET | `/api/portfolio` | Cash, positions, valuation |
| POST | `/api/portfolio/trade` | Execute a market order |
| GET | `/api/portfolio/history` | Portfolio value snapshots |
| GET | `/api/portfolio/trades` | Trade log (most recent first) |
| GET/POST | `/api/watchlist` | List / add a ticker |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |
| POST | `/api/chat` | Chat with the AI (auto-executes trades) |
| GET | `/api/chat/history` | Last 20 chat messages |

## Backend Development

```bash
cd backend
uv sync --extra dev
uv run --extra dev pytest          # 144 tests
uv run --extra dev ruff check app/ tests/
uv run --extra demo market_data_demo.py
```

See [`backend/README.md`](backend/README.md) for the market data API.

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

Tapetide is capped at 400 calls/day, about 13 minutes of continuous polling, so use it for short demo sessions.

## Project Structure

```
frontend/    Next.js static export (to build)
backend/     FastAPI uv project (built)
  app/       API routes, db, portfolio, chat, market data
  db/         schema.sql
  tests/     144 backend + API tests
planning/    Plan, status, and agent contracts (start with PLAN.md)
scripts/     Start/stop helpers (built)
test/        Playwright E2E tests (to build)
db/          SQLite file at runtime
```

## License

See [LICENSE](LICENSE).
