# FinAlly — AI Trading Workstation

A visually stunning AI-powered trading workstation that streams live market data, simulates portfolio trading, and integrates an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — Rs 10 lakh virtual cash, market orders, instant fills
- **Portfolio visualizations** — heatmap (treemap), P&L chart, positions table
- **AI chat assistant** — analyzes holdings, suggests and auto-executes trades
- **Watchlist management** — track tickers manually or via AI
- **Dark terminal aesthetic** — Bloomberg-inspired, data-dense layout

## Architecture

Single local process serving everything on port 8000, no Docker:

- **Frontend**: Next.js (static export) with TypeScript and Tailwind CSS
- **Backend**: FastAPI (Python/uv) with SSE streaming
- **Database**: SQLite with lazy initialization
- **AI**: LiteLLM → Groq (`groq/openai/gpt-oss-120b`) with structured outputs
- **Market data**: Built-in GBM simulator (default) or Tapetide MCP for real NSE data during trading hours (optional)

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Add your GROQ_API_KEY to .env

# Build the frontend and launch the backend
./scripts/start_mac.sh      # macOS/Linux
./scripts/start_windows.ps1 # Windows

# Open http://localhost:8000
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for AI chat |
| `TAPETIDE_API_KEY` | No | Tapetide MCP bearer token for real NSE market data; omit to use simulator |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (testing) |

## Project Structure

```
finally/
├── frontend/    # Next.js static export
├── backend/     # FastAPI uv project
├── planning/    # Project documentation and agent contracts
├── test/        # Playwright E2E tests
├── db/          # SQLite file (runtime)
└── scripts/     # Start/stop helpers
```

## License

See [LICENSE](LICENSE).
