# FinAlly — Agent Team Coordination Board

Shared status + issue board for the build team. Agents append here; the orchestrator reads it.
PLAN.md is the authoritative contract. STATUS.md is the authoritative build status.

## Roster

- **Frontend Engineer** — builds `frontend/` (Next.js static export, §10). Critical path.
- **Backend Engineer** — owns live correctness of `backend/app/` REST + SSE vs §8. Fixes integration issues.
- **Database Engineer** — owns `backend/db/` + `app/db.py`: schema, seed, queries, fresh-DB bootstrap.
- **LLM Engineer** — owns `app/chat.py` + Groq/LiteLLM integration, mock mode, SEBI, action ordering (§9).
- **Integration Tester** — builds/runs Playwright E2E in `test/` (§12); reports issues back here.

## Ground rules

- Backend/DB/LLM are already built and tested (144 pytest passing). Do NOT rewrite working code
  without a proven root cause. Verify-live, then stand by for integration fixes.
- Run backend instances on your own `PORT` + `DATABASE_PATH` + `FINALLY_PID_FILE` to avoid collisions
  (plan supports this via env vars, §5/§11). Use `LLM_MOCK=true` + `MARKET_DATA_SOURCE=simulator`
  for deterministic checks unless verifying real Groq/Tapetide.
- The frontend talks only to `/api/*` and `/api/stream/prices`, same origin. API contract = §8.

## Status log

(append dated entries below)

### 2026-10-20 — Frontend Engineer: `frontend/` complete

Built the full Next.js static-export trading terminal. Build, lint, unit tests all green;
verified live against the backend (`LLM_MOCK=true`, `MARKET_DATA_SOURCE=simulator`, port 8099).

**Stack:** Next.js 16.4.2 (App Router, `output: 'export'`), React 19, TypeScript strict,
Tailwind v4, Lightweight Charts v5, Vitest + React Testing Library.

**Commands (run from `frontend/`):** `npm install` → `npm run build` (emits `frontend/out/`,
which the backend static-mounts) → `npm run lint` → `npm test`.

**Panels built (all §10):** Header (live total value, connection dot, LIVE/SIMULATED badge,
`market_data_healthy` freshness badge, cash), Trade bar (prefills from selection, decimal qty),
Watchlist (membership from `GET /api/watchlist`, prices merged from SSE, per-row flash on
`direction != "flat"`, sparkline, add/remove, click-to-select), Main chart (live-since-load,
SSE-accumulated, remounts per ticker), Portfolio Value chart (`/api/portfolio/history`), self-
rendered Heatmap (positions-only weight, P&L tint), Positions table, Recent Trades
(`/api/portfolio/trades`), AI chat (loads `/api/chat/history` on mount, input disabled while
pending, refetches portfolio+watchlist when `actions` non-empty, keeps text on 502).

**Live-verified end to end:** SSE streaming + flash, manual buy/sell, mocked chat
("buy 1 INFY") executing inline with post-turn refetch, heatmap/positions/P&L updating,
data-source badge + freshness. Zero console errors.

**Notes for Integration Tester:**
- SSE buffer is aggregated to one point/second (last wins) and capped at 900 points before
  feeding Lightweight Charts (strictly-ascending-unique requirement). Charts are client-only
  (`lightweight-charts` dynamically imported inside the effect) so static prerender never loads it.
- Health is polled every 5s; portfolio+history every 15s; both also refetched after any trade or
  AI action. There is no `data-testid` attribute set yet — E2E selectors currently rely on text
  (ticker symbols, "Buy"/"Sell"/"Send"/"Add" buttons, panel headings, `aria-label="Remove <T>"`).
  If stable hooks are wanted, ask and I'll add `data-testid`s.
- Backend contract matched exactly as written in §8 — no deviations or missing fields found.
- ESLint note: Next 16's `react-hooks/set-state-in-effect` flags the on-mount data fetch in
  `AppDataProvider`; it's suppressed on that one line (legitimate for a static SPA with no server
  loader).

### 2026-10-20 — Database Engineer: DB layer verified against PLAN §7 (no changes made)

Verified `backend/db/schema.sql` + `backend/app/db.py` against §7. All conformant; no code changes.

Schema conformance checklist vs §7:
- users_profile: keyed by `id` (no separate user_id), cash_balance REAL DEFAULT 1000000.0, created_at TEXT. OK
- watchlist: id PK, user_id DEFAULT 'default', ticker, added_at, UNIQUE(user_id,ticker). OK
- positions: id PK, user_id, ticker, quantity REAL, avg_cost REAL, updated_at, UNIQUE(user_id,ticker). OK
- trades: id PK, user_id, ticker, side, quantity REAL, price REAL, executed_at (append-only). OK
- portfolio_snapshots: id PK, user_id, total_value REAL, recorded_at. OK
- chat_messages: id PK, user_id, role, content, actions TEXT (nullable), created_at. OK
- Ticker normalization (strip().upper()) applied at the logic boundary — portfolio.py:89, watchlist.py:25 — then stored normalized, so the UNIQUE(user_id,ticker) constraint can't be defeated by case. OK
- Timestamps stored UTC ISO-8601 with offset via `now_iso()` (datetime.now(timezone.utc).isoformat()). OK

Fresh-DB bootstrap (live, isolated DB on port 8012, LLM_MOCK + simulator):
- 1 users_profile row, cash_balance=1000000.0. OK
- Exactly 10 watchlist rows in documented order (HEROMOTOCO..TATAMOTORS), added_at strictly increasing (~1ms apart). OK
- 1 portfolio_snapshots startup row (total_value=1000000.0). OK

Position math (live via /api/portfolio/trade):
- Buy sets avg_cost = fill price; qty aggregates (10+5=15). OK
- Second buy at a distinct price re-averages: (4*1211.25 + 6*1211.45)/10 = 1211.37. OK
- Partial sell reduces qty, leaves avg_cost unchanged. OK
- Sell-to-zero deletes the position row. OK
- Epsilon exit: 0.1*3 = 0.30000000000000004, sell 0.3 (residual ~5.5e-17 < 1e-9) deletes row, no ghost. OK
- Trade executed_at is UTC ISO-8601 with +00:00 offset. OK
- Untracked ticker trade -> HTTP 400. OK

No mismatches found. DB layer stands as-is; standing by for integration fixes.

### 2026-10-20 — Backend Engineer: live API verification vs PLAN.md §8

- `uv run --extra dev pytest` -> **144 passed**. No code changes made; no discrepancies requiring a fix found.
- Booted live (`LLM_MOCK=true`, `MARKET_DATA_SOURCE=simulator`, isolated port 8011 + temp DB), smoke-tested every endpoint field-for-field against §8. All verified:
  - GET /api/health -> `{status, data_source, market_data_healthy}` exact.
  - GET /api/portfolio, /history (bare array asc), /trades (bare array) -> shapes exact.
  - GET /api/watchlist -> `{tickers:[...]}` ordered by added_at; nulls for unpriced.
  - POST /api/watchlist: valid add 200, duplicate idempotent 200 (same added_at), invalid 400 `{"error":"No stock with ticker ZZZZ exists"}`.
  - DELETE /api/watchlist/{ticker}: `{ticker, removed}`; idempotent (removed:false); URL-encoded `M%26M` and `BAJAJ-AUTO` decode correctly.
  - POST /api/portfolio/trade: buy/sell/sell-to-zero (position row deleted, positions empty), untracked ("Only tickers in your watchlist... Add SBIN to your watchlist first." verbatim), zero/negative qty, insufficient cash, insufficient shares -> all correct 400 `{"error":...}`.
  - POST /api/chat (mock) + GET /api/chat/history -> `{message, actions[]}` shape exact; history oldest-first, user.actions null, assistant carries actions; no SEBI disclaimer under simulator (correct).
  - Error envelope normalized to `{"error":...}` including Pydantic 422 -> **400** (`{"error":"ticker: Field required"}`).
  - SSE GET /api/stream/prices: ~500ms cadence, full 10-ticker price map per frame, each entry = full `PriceUpdate.to_dict()`.
- **Note for Frontend (not a bug):** watchlist/SSE `change_percent` and `day_change_percent` carry **4 dp** (e.g. `0.1768`), not 2 dp. §8's "percentages to 2 dp" general rule is superseded for price fields by `PriceUpdate.to_dict()`, which §6 + backend/CLAUDE.md name as the source-of-truth contract. Frontend should format for display. Money/price fields and portfolio percentages (return_percent) are 2 dp as specified.
- **Minor note (not fixing):** "no price available" message uses ASCII hyphen (`yet - try again`) vs §8's em-dash. Punctuation only; do not depend on exact dash in the UI.

### 2026-10-20 — Backend Engineer: fixed flaky `test_custom_update_interval` (Windows timing)

- **Root cause proven:** `tests/market/test_simulator_source.py::test_custom_update_interval` used `update_interval=0.01` (10ms) + `sleep(0.05)` and asserted `version > initial+2` (>=3 ticks). Windows' ~15.6ms timer resolution fires a 10ms asyncio interval only ~2-3x in 50ms, so the fixed-count assertion was too tight. Reproduced the flake at **1/10 runs** on this machine. Product code is correct; only the test's timing assertion was wrong.
- **Fix (minimal, intent-based):** run a fast source (0.01s) and a slow source (0.1s) over the same 0.3s window and assert `fast_ticks > slow_ticks`. This verifies the custom interval is actually honored (shorter interval -> more ticks) without a host-timer-dependent fixed count, and is stronger than loosening to `> initial_version`.
- **Verified:** target test **0/15** failures after the fix; full suite `uv run --extra dev pytest` -> **145 passed** (count rose vs the earlier 144 due to a concurrent teammate test addition; my change was a 1-for-1 test replacement).

### 2026-10-20 — LLM Engineer: §9 chat integration verified (CONFORMANT, no fixes)

Verified `backend/app/chat.py` + `routes/chat.py` against PLAN.md §9 in mock mode (live) and via
the unit suite. No mismatches found; no code changed.

- Tests: `uv run --extra dev pytest -k "chat or api"` -> 26 passed. (Full suite per STATUS.md: 144.)
- Groq calling pattern matches groq-skill exactly: `groq/openai/gpt-oss-120b`, tenacity
  `@retry(wait_exponential(min=2,max=60), stop_after_attempt(5))`, `response_format=LLMResponse`,
  `reasoning_effort="low"`, `model_validate_json`. Real Groq path exercised off the event loop via
  `asyncio.to_thread`. Did NOT spend real Groq budget — covered by mock + unit tests (STATUS.md
  notes it was validated against real Groq earlier).
- Live mock table (port 8013, LLM_MOCK=true, simulator): buy watchlist ticker -> executes + position
  appears; sell held ticker -> executes; "add WIPRO" -> validate_ticker passes, added; "remove
  WIPRO" -> removed; generic -> canned summary, 0 actions; "add SOME" -> naive extraction proposes
  SOME, rejected at validate_ticker ("No stock with ticker SOME exists"), harmless. Response shape
  = {message, actions} only (no portfolio payload, §8). /api/chat/history repopulates oldest-first,
  interleaved user/assistant.
- Execution order (adds -> trades -> removals) correct by inspection (`_auto_execute`); each action
  isolated (per-action try/except, status executed/failed+error). Not drivable via a single mock
  turn (mock emits one action/turn), so no live multi-action proof.
- SEBI: exact text appended only when `data_source=="tapetide"`, de-duped on exact string, absent
  under simulator, appended BEFORE persist (history shows post-disclaimer text). Covered by
  test_chat_appends_sebi_disclaimer_under_tapetide / test_chat_no_sebi_disclaimer_under_simulator.
- 502 non-persist path: correct by inspection — `handle_chat` calls `_generate` (raises ChatError)
  before either `insert_chat`, route maps ChatError->502, so no row is written.

### 2026-10-20 — LLM Engineer: added 502-non-persist regression test

Closed the coverage gap noted above. Added
`test_chat_upstream_failure_returns_502_and_persists_nothing` to `backend/tests/test_api.py`:
monkeypatches `app.chat._generate` to raise `ChatError` (simulates Groq timeout/error/unparseable),
asserts POST /api/chat -> 502 with the `{"error": ...}` envelope, and that the chat_messages row
count is unchanged before/after (no half-turn persisted, §8). Suite green: `pytest -k "chat or api"`
-> 27 passed; full suite -> 145 passed. No production code changed.

### 2026-10-20 — Integration Tester: Playwright E2E suite built, all 7 scenarios green

Built the Playwright E2E suite in `test/` per §12. All 7 Key Scenarios pass against the full
local app (FastAPI serving `frontend/out/`), run serially on port 8200 with mandatory isolation.

**Harness:** Playwright `webServer` fixture launches the backend itself
(`uv run uvicorn app.main:app --port 8200`, cwd `backend/`) with `LLM_MOCK=true`,
`MARKET_DATA_SOURCE=simulator`, and a **per-run** `DATABASE_PATH` under `test/.e2e/`
(`finally-<ts>.db`). Per-run unique DB (not a delete-before) because the backend opens+locks
the SQLite file at startup, so deleting it in a globalSetup races the server and hit `EPERM` —
a fresh filename sidesteps that and keeps the seeded state deterministic. `workers: 1`,
`reuseExistingServer: false`. Never touches the user's `db/finally.db`, `.finally.pid`, or 8000.

**Run:** `cd test && npm install && npx playwright install chromium && npm test`.

**Scenarios (all pass):** 01 fresh-start (10-ticker watchlist, Rs 10,00,000 cash, streaming +
changing prices), 02 watchlist add(WIPRO)/remove, 03 buy (cash down, position row, qty via API),
04 sell-to-zero (row disappears, cash up), 05 visualization (heatmap tinted cell with rgba bg,
Portfolio Value chart canvas present + not "No data yet."), 06 mocked chat "buy 1 INFY"
(inline ✓ action line + post-turn portfolio refetch), 07 SSE prices keep updating over time.

**Selectors:** text/role/aria only, no data-testid needed. One genuine ambiguity worth noting
for the Frontend Engineer (worked around, not blocking): the trade-bar ticker input
(placeholder "Ticker") and the watchlist add input (placeholder "Add ticker…") both match a
substring `getByPlaceholder("Ticker")`; resolved with `{ exact: true }`. If stable hooks are
ever wanted, a `data-testid` on the trade-bar inputs would be the cleanest, but not required.

**Defects found: none.** Every panel and API behavior matched §8/§9/§10 as written. No product
code changed; the only fixes were to my own test selectors.

## Issues

(integration tester logs defects here; owning engineer marks resolved)

No product defects found during E2E. Suite is green end-to-end.
