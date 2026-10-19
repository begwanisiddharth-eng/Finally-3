# FinAlly — Build Status

Live status of what is built vs. still to build. This is the single place build status lives;
PLAN.md §4 stays a stable description of the *target* layout and does not track status. Update
this file as components land. Always confirm against the filesystem — this file can lag reality.

**Last updated:** 2026-10-19

## Done

- **Market data subsystem** (`backend/app/market/`) — complete, tested, reviewed. 10 modules:
  models, cache, interface, simulator, tapetide_client, nse_hours, factory, manager, stream,
  seed_prices. Live Tapetide↔simulator handover, day-change tracking, `MARKET_DATA_SOURCE`
  override, and `active_source_name` labels. Also: Tapetide MCP calls serialized through an
  `asyncio.Lock`; naive upstream timestamps parsed as IST; `validate_ticker` raises
  `MarketDataError` on transport failure (vs. returning a false "not found"). See
  `planning/MARKET_DATA_SUMMARY.md` for detail.
- **Backend test suite** (`backend/tests/market/`) — 8 modules, `uv run pytest` → 107 passed.
- **Repo scaffolding** — `.github/` CI workflows, `.gitignore`, `.env.example`, both READMEs,
  `backend/pyproject.toml` (+ `uv.lock`), `backend/market_data_demo.py`.

## To build

- **`backend/app/main.py`** — FastAPI entrypoint: `load_dotenv()`, repo-root path resolution
  (§11), lifespan init/shutdown ordering (§7), `MarketDataManager` wiring, API routers, static
  mount. Also hosts the Tapetide degraded-mode fallback — the `_force_fallback` + `retry_after`
  cooldown latch on the manager (§6, N=3, 5-min cooldown) — which is specified but not yet coded;
  and the API mapping of `MarketDataError` to `503` on the validation path (§6/§8).
  Implementation-ready spec for the remaining market-data work (degraded-mode counter + latch,
  MCP tool-error detection, call timeouts, health freshness, SSE router fix, tracked-ticker
  helpers): `planning/MARKET_DATA_DESIGN.md` §18.
- **`backend/db/`** — schema, lazy/lifespan init, and row seeding for the five tables (§7),
  via `aiosqlite`.
- **API endpoints** — portfolio, watchlist, chat, health (§8), with the `{"error": ...}`
  envelope and response shapes from §8.
- **LLM integration** — groq-skill via LiteLLM, structured outputs, auto-execution + ordering,
  server-side SEBI enforcement, `LLM_MOCK` mode (§9). Needs `uv add litellm pydantic tenacity`.
- **`frontend/`** — Next.js static export (App Router, `output:'export'`, TS strict), Tailwind
  dark theme, Lightweight Charts + Recharts Treemap, all §10 panels.
- **`scripts/`** — `start`/`stop` for macOS/Linux and Windows (§11).
- **`test/`** — Playwright E2E with the isolation env from §12.
- **`db/.gitkeep`** — top-level runtime DB directory placeholder.
