# FinAlly — AI Trading Workstation

An AI-powered trading workstation that streams live market data, simulates portfolio trading with Rs 10 lakh of virtual cash, and includes an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Status

Work in progress. See [`planning/STATUS.md`](planning/STATUS.md) for what is built.

- **Done**: market data subsystem (simulator, Tapetide client, live handover) and its test suite (107 tests), in `backend/`
- **To build**: FastAPI app (`main.py`), database, API, LLM chat, frontend, start/stop scripts, E2E tests, Tapetide failure fallback to the simulator

The Quick Start below describes the target experience and will work once the remaining pieces land.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — market orders, instant fills, no fees
- **Portfolio visualizations** — heatmap, P&L chart, positions table
- **AI chat assistant** — analyzes holdings, suggests and auto-executes trades
- **Watchlist management** — manually or via AI
- **Dark terminal aesthetic** — Bloomberg-inspired, data-dense layout

## Architecture

Single local process serving everything on port 8000, no Docker:

- **Frontend**: Next.js (static export), TypeScript, Tailwind CSS
- **Backend**: FastAPI (Python, managed with `uv`), SSE streaming
- **Database**: SQLite (`db/finally.db`)
- **AI**: LiteLLM → Groq (`groq/openai/gpt-oss-120b`) with structured outputs
- **Market data**: built-in GBM simulator by default; real NSE data via the Tapetide MCP server during trading hours if `TAPETIDE_API_KEY` is set

## Prerequisites

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js LTS and npm
- Windows only: the `.ps1` scripts may need `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Quick Start

```bash
./scripts/start_mac.sh        # macOS/Linux
.\scripts\start_windows.ps1   # Windows (PowerShell)
```

The script creates `.env` from `.env.example` if missing (set `GROQ_API_KEY` in it), builds the frontend, starts the backend, and prints the URL: http://localhost:8000. Use `scripts/stop_mac.sh` or `scripts/stop_windows.ps1` to stop; the database persists across runs. Pass `--build` to force a frontend rebuild.

## Backend Development

The market data subsystem can be exercised today:

```bash
cd backend
uv sync
uv run pytest
uv run --extra demo market_data_demo.py
```

See [`backend/README.md`](backend/README.md) for details.

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
backend/     FastAPI uv project (market data done)
planning/    Plan, status, and agent contracts (start with PLAN.md)
scripts/     Start/stop helpers (to build)
test/        Playwright E2E tests (to build)
db/          SQLite file at runtime (to build)
```

## License

See [LICENSE](LICENSE).
