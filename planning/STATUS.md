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
- **Tapetide degraded-mode fallback** (§6) — `MarketDataSource.is_degraded()`;
  `TapetideDataSource` counts consecutive poll failures (N=3) and treats a dead poll task as
  degraded; `MarketDataManager` falls back to the simulator and holds a `_force_fallback` /
  `_retry_after` latch (5-min cooldown) so it cannot flap. The supervisor ticks at least every 5s.
- **`backend/app/main.py`** — FastAPI entrypoint: `load_dotenv()`, repo-root path resolution
  (§11), lifespan init/shutdown ordering (§7), `MarketDataManager` wiring, all API routers, the
  normalized `{"error": ...}` envelope, SSE route reading the cache from `app.state`, and the
  static mount (served only when `frontend/out/` exists). Health freshness via a new
  `PriceCache.seconds_since_update()`.
- **`backend/db/`** — `schema.sql` for the five tables (§7); init + seeding + all queries in
  `app/db.py` via `aiosqlite`.
- **API endpoints** — portfolio, watchlist, chat, health (§8), with the `{"error": ...}`
  envelope and response shapes from §8. Logic in `app/portfolio.py`, `app/watchlist.py`,
  `app/chat.py`, `app/routes/`.
- **LLM integration** — groq-skill via LiteLLM, structured outputs, auto-execution + ordering
  (adds -> trades -> removals), server-side SEBI enforcement, `LLM_MOCK` mode (§9). Validated
  against the real Groq API and in mock mode.
- **`scripts/`** — `start`/`stop` for macOS/Linux and Windows (§11): .env bootstrap, GROQ check
  (skipped under `LLM_MOCK`), already-running/stale-PID handling, health poll. Idempotent.
- **Backend + API test suite** — `uv run --extra dev pytest` → 136 passed (119 market +
  17 API integration via FastAPI TestClient running the lifespan).
- **`db/.gitkeep`** — top-level runtime DB directory placeholder.
- **Repo scaffolding** — `.github/` CI workflows, `.gitignore`, `.env.example`, both READMEs,
  `backend/pyproject.toml` (+ `uv.lock`), `backend/market_data_demo.py`.

## To build

- **`frontend/`** — Next.js static export (App Router, `output:'export'`, TS strict), Tailwind
  dark theme, Lightweight Charts, self-rendered heatmap, all §10 panels. Not yet started; the
  backend serves the API only until this lands.
- **`test/`** — Playwright E2E with the isolation env from §12 (depends on the frontend).
