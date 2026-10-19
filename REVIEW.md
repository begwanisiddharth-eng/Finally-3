# FinAlly - Code Review & Test Report

**Date:** 2026-10-19
**Scope:** Full codebase review with emphasis on the backend. Bugs fixed, missing backend
functionality developed, end-to-end testing performed.
**Reviewer:** Automated code review (Claude Code)

---

## 1. Summary

Before this pass, only the **market data subsystem** (`backend/app/market/`) existed - complete and
well-tested (119 tests). Everything else in the backend contract (PLAN.md sections 7-9, 11) was
unbuilt: no database, no API endpoints, no LLM chat, no `main.py`, no start/stop scripts.

This review **built the entire remaining backend**, fixed one pre-existing test bug, and verified
the result end-to-end over real HTTP (including SSE), against the real Groq LLM, and via the
start/stop scripts. The backend is now fully functional and serves every `/api/*` endpoint in
PLAN.md section 8.

**Test result: 138 passed (119 market + 19 API integration), 0 failed. Lint clean.**

The only remaining work is the **frontend** (`frontend/`) and the **Playwright E2E suite**
(`test/`), which depends on the frontend. These are called out in section 6.

---

## 2. Review of the existing market data subsystem

The market subsystem was reviewed module by module. It is high quality: a clean
`MarketDataSource` abstraction, a shared `PriceCache` that is never replaced across handovers,
correct GBM math, correlated moves via Cholesky, the degraded-mode fallback latch, and
IST-aware timestamp parsing. It conforms to the PLAN contracts it claims.

### 2.1 Bug fixed: flaky, environment-dependent handover test

`tests/market/test_manager.py::test_supervise_triggers_handover_on_interval` failed on this
machine (and is latently flaky everywhere).

- **Root cause (proven, not guessed):** the test let the supervisor hand over to a **real**
  `TapetideDataSource`, then asserted the active source was still Tapetide after 150 ms. On this
  Windows + Python 3.13 build, `httpx2`'s default `truststore` SSL context fails immediately
  (`ssl.SSLError: [SSL] unknown error (_ssl.c:3138)`), so the Tapetide poll task crashed, which
  correctly set `is_degraded() == True`, and the supervisor (ticking every 50 ms) correctly fell
  back to the simulator **before** the assertion ran. The app logic behaved exactly as designed;
  the test was asserting against a race it did not control.
- **Fix:** stub `TapetideDataSource._run` with a no-op sleep for that test so the handover is
  observed without depending on a live MCP/SSL connection. The other handover tests call
  `_maybe_handover()` once and check immediately, so they were never affected.

### 2.2 Observation (not a code bug): httpx2 / truststore SSL on this host

The same SSL error means the **real Tapetide path cannot connect on this particular machine**.
This is environmental (a `truststore` + Python 3.13 interaction on Windows), not a defect in the
FinAlly code. It does not affect the simulator, which is the default and the entire E2E path. If
real NSE data is wanted on this host, verify by constructing the `httpx2.AsyncClient` with an
explicit `ssl` context (bypassing `truststore`) - tracked as a follow-up, deferred because
Tapetide is optional.

### 2.3 Additive change to `PriceCache`

Added `PriceCache.seconds_since_update()` (and an internal `_last_write` wall-clock stamp) to back
the `/api/health` freshness check (PLAN section 6). Purely additive; no existing behavior or test
changed.

---

## 3. Backend functionality developed

All of the following was missing and is now implemented, following PLAN.md and the global code
style (short modules, minimal defensive code, latest APIs, `aiosqlite`, no ORM).

| Area | Files | Notes |
|---|---|---|
| Database layer | `backend/db/schema.sql`, `backend/app/db.py` | 5 tables, lifespan init + idempotent seed, all queries via `aiosqlite`. WAL mode. UTC ISO-8601 timestamps. Seed watchlist stamped with strictly increasing `added_at`. |
| Request/LLM schemas | `backend/app/schemas.py` | Pydantic models incl. the structured-output schema. |
| Portfolio service | `backend/app/portfolio.py` | Trade execution + valuation. Weighted `avg_cost` on buy, unchanged on sell, float epsilon for zero/insufficient, position deleted at zero, price-cache gating. |
| Watchlist service | `backend/app/watchlist.py` | Add (validate + idempotency short-circuit), remove (keeps pricing a still-held ticker). |
| LLM chat | `backend/app/chat.py` | LiteLLM -> Groq structured outputs with tenacity retry; deterministic `LLM_MOCK` mode; deterministic auto-execution (adds -> trades -> removals); server-side SEBI enforcement. |
| API routers | `backend/app/routes/` (`portfolio`, `watchlist`, `chat`, `health`) + `routes_helpers.py` | All of section 8. State on `app.state`. |
| App entrypoint | `backend/app/main.py` | `load_dotenv`, repo-root paths, lifespan ordering (section 7), `{"error": ...}` envelope for HTTP/validation/500, SSE route, static mount (only if `frontend/out/` exists). |
| Start/stop scripts | `scripts/start_windows.ps1`, `stop_windows.ps1`, `start_mac.sh`, `stop_mac.sh` | .env bootstrap, GROQ check (skipped under `LLM_MOCK`), already-running/stale-PID handling, health poll. Idempotent. |
| Dependencies | `backend/pyproject.toml` | Added `aiosqlite`, `litellm`, `pydantic`, `tenacity`. |

---

## 4. Contract conformance verified

Each of these was confirmed by an automated test and/or a live HTTP call:

- **Error envelope** `{"error": ...}` for 400 business errors, 422 request-validation, and 500.
- **Status codes:** 200 for successful GETs, trades, and idempotent watchlist mutations; 400 for
  business errors; 502 for chat upstream failure; 503 for a watchlist validation that cannot reach
  Tapetide (vs. 400 "invalid ticker").
- **Ticker normalization** (`strip().upper()`) at every boundary, incl. URL-decoded DELETE path.
- **Watchlist idempotency** - duplicate add returns 200; delete of an absent ticker returns 200
  with `removed: false`.
- **Trade gating** - a ticker not tracked (watchlist union positions) is rejected with the exact
  "Add X to your watchlist first" message; a tracked-but-unpriced ticker is rejected distinctly.
- **Portfolio math** - weighted avg cost on buy, avg cost unchanged on sell, position row deleted
  on a sell to zero, and the ticker's price source stopped when it is no longer watched or held.
- **Startup snapshot** - `/api/portfolio/history` has at least one point immediately on a fresh DB.
- **Default watchlist** - the 10 seed tickers appear in the exact PLAN order.
- **SEBI disclaimer** - absent under the simulator; appended verbatim when the active source is
  `tapetide` (verified by forcing the source label in a test).
- **Chat auto-execution** - mock and real Groq both parse structured output and execute the trade;
  `/api/chat/history` persists the turn with its actions.

---

## 5. Testing performed

### 5.1 Unit + API integration (automated)

`uv run --extra dev pytest` -> **138 passed**:
- 119 market subsystem tests (unchanged behavior, one flaky test repaired).
- 19 new API integration tests (`tests/test_api.py`) driving the real app through FastAPI's
  `TestClient`, which runs the lifespan so the database, market manager, and snapshot task are all
  live. Covers health, watchlist CRUD + validation + idempotency, buy/sell/sell-to-zero, all four
  trade-rejection paths, history, trade log ordering, mock-chat trade + watchlist flows, chat
  history persistence, the 503 transport path, and the SEBI append.

`uv run --extra dev ruff check app/ tests/` -> **All checks passed.**

### 5.2 Live end-to-end (real process, real HTTP)

Launched `uvicorn app.main:app` as a real process (simulator + mock LLM, isolated DB/port) and
exercised it over HTTP:
- `/api/health` -> `{"status":"ok","data_source":"simulator","market_data_healthy":true}`.
- Buy 10 HDFCBANK filled at the live cache price; cash decreased; totals consistent.
- `/api/chat` ("buy TCS") auto-executed a trade and returned the action inline.
- An untracked-ticker trade returned HTTP 400.
- `/api/stream/prices` delivered ~4 SSE frames in 1.5 s (the ~500 ms simulator cadence).

### 5.3 Real Groq LLM path

Ran `handle_chat` against the **real** Groq API (not mock) with "Buy 5 shares of HDFCBANK":
the model returned valid structured JSON, which parsed and auto-executed the trade. This confirms
the LiteLLM -> Groq structured-output integration, not just the mock.

### 5.4 Start/stop scripts

`start_windows.ps1` -> built nothing (no frontend), synced backend, launched uvicorn, polled
health, printed the URL. A second run reported "already running". `stop_windows.ps1` stopped the
process and removed the PID file; a second stop exited cleanly. All idempotent, isolated via
`FINALLY_PID_FILE` and `PORT`.

---

## 6. Remaining work

- **Frontend (`frontend/`)** - not started. The Next.js static-export SPA with all section-10
  panels (watchlist, charts via Lightweight Charts, self-rendered heatmap, positions, trade bar,
  chat) is the main outstanding deliverable. Until it exists, the start scripts launch the API
  only and `main.py` logs "serving API only".
- **Playwright E2E (`test/`)** - deferred; it drives the browser UI, so it depends on the
  frontend. The section-12 scenarios are already covered at the API level by `tests/test_api.py`;
  the browser layer is what remains.
- **Tapetide live verification** - the simulator path is fully exercised. The live Tapetide path
  is covered by source-level unit tests but was not run against the real MCP server during trading
  hours (and is blocked on this host by the `httpx2`/`truststore` SSL issue in section 2.2).

---

## 7. Notes on design decisions honored

- **Realized P&L is intentionally not tracked** (PLAN section 7): `trades` stores no cost basis and
  `avg_cost` is overwritten on the next buy. Nothing in the UI contract needs it. Left as designed.
- **Money stored as float** and **no special SQLite concurrency handling** - both are explicit
  PLAN decisions (section 13) and were kept.
- **Static mount is graceful when the frontend is absent** - a deliberate deviation from the
  section-11 "assert the static dir exists" note, so the backend is runnable and testable on its
  own before the frontend lands. When `frontend/out/` exists it is mounted at `/` after all
  `/api/*` routes, exactly as specified.
