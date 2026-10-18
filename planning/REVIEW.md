# FinAlly — Review of `planning/PLAN.md`

**Date:** 2026-10-18
**Scope:** `planning/PLAN.md` (484 lines), reviewed against the current repository state
(`backend/`, `README.md`, `backend/CLAUDE.md`, `planning/MARKET_DATA_SUMMARY.md`, `planning/archive/`).

---

## 1. Summary

The plan is unusually well-written for an agent-built project: it is opinionated, mostly
self-consistent, and the "why these choices" table plus the mock-LLM table make the contract
between agents clear. It reads as a genuine specification rather than a wish list.

However, the plan was recently rewritten (`git status` shows `PLAN.md` modified on top of the
single `Initial commit`) from a Docker / OpenRouter-Cerebras / Massive-Polygon / US-ticker design
to a no-Docker / Groq / Tapetide-MCP / NSE-ticker design. The **already-built and
already-reviewed market-data component was built against the old design**, and the supporting
docs (`README.md`, `backend/CLAUDE.md`) still describe the old one. So the single most important
finding is not internal to the plan text — it is that the plan and the code now disagree about
the datasource, the tickers, the LLM provider, and the run model.

There are also a handful of genuine internal specification bugs (§4 below), the most concrete
being that the ticker-validation policy in §6 is unimplementable against the built simulator, and
that the mock-LLM "add" scenario in §9 is self-contradictory.

**Verdict:** resolve the blocking items in §3 before any further agent work. The plan is close;
it needs reconciliation with reality, not a rewrite.

---

## 2. What the plan gets right

- Clear single-process, single-port, no-Docker architecture with a matching rationale table (§3).
- The `MarketDataSource` abstraction, shared `PriceCache`, and SSE fan-out (§6) mirror what was
  actually built and are easy for downstream agents to consume.
- Explicit, machine-checkable contracts: HTTP 400 + `{"error": ...}` shape for trade/watchlist
  failures (§8), and a structured output schema for the LLM (§9).
- Lazy SQLite init with no migration step (§7) is a good fit for a demo tool.
- The mock-LLM table (§9) is exactly the right level of detail for deterministic E2E tests.
- Honest scoping: cloud deployment explicitly out of scope (§11); auto-execution trade-off called
  out rather than hidden (§9).

---

## 3. Blocking issues (resolve before proceeding)

### 3.1 The plan contradicts the completed market-data component

`planning/MARKET_DATA_SUMMARY.md` declares the market-data subsystem "Complete, tested, reviewed,
all issues resolved." That subsystem is:

- `MassiveDataSource` — a **Polygon.io REST poller** via the `massive` package
  (`backend/app/market/massive_client.py`, `backend/app/market/factory.py:24`).
- Seeded with **US tickers** — AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX
  (`backend/CLAUDE.md`; `seed_prices.py`).
- Selected by `MASSIVE_API_KEY`.

`PLAN.md` now specifies:

- **Tapetide MCP** as the real datasource (§6), selected by `TAPETIDE_API_KEY`.
- **NSE tickers** — HEROMOTOCO, BEL, PIDILITIND, LTF, HDFCBANK, INFY, RELIANCE, TCS, ICICIBANK,
  TATAMOTORS (§7).
- A test obligation to cover "Tapetide MCP response parsing" and "NSE-trading-hours gating" (§12)
  — none of which exist; the tests that exist cover Massive parsing.

`CLAUDE.md` (project root) tells agents the market-data component "has been completed" and the
"remainder of the platform is still to be developed." An agent reading the plan alongside that
statement will build on a datasource the plan says not to use.

**Decision required:** either (a) re-apply the plan's new design to the built component (rewrite
`MassiveDataSource` → Tapetide MCP client, swap seed tickers to NSE, update factory + tests +
`backend/CLAUDE.md` + `MARKET_DATA_SUMMARY.md`), or (b) revert the plan's datasource/ticker
change. Leaving both in place guarantees downstream agents build against the wrong contract.

### 3.2 Stale supporting docs disagree with the plan

`README.md` still describes: "Single Docker container", "OpenRouter (Cerebras inference)",
"Massive API", and "$10k virtual cash". `backend/CLAUDE.md:32,45` still says the factory returns
`MassiveDataSource` when `MASSIVE_API_KEY` is set and that the default tickers are the US set.
These are not plan files, but they are the documents agents and humans actually read. They must
be updated in the same change that resolves 3.1, or they will keep injecting the old design.

### 3.3 Ticker validation (§6) cannot work as specified against the simulator

§6 says adding a ticker is "validated against the active market data source (simulator's known
universe ...)". The built simulator has **no known universe**: `SimulatorDataSource.add_ticker`
(`backend/app/market/simulator.py:242`) accepts any string and seeds unknown tickers with
`random.uniform(50.0, 300.0)` and `DEFAULT_PARAMS`
(`simulator.py:151-152`). So under the default simulator, *every* ticker is "recognized" and the
validation in §6/§8 is a no-op — yet §12 expects a test that "Add and remove a ticker" and §9
expects rejection of unknown tickers.

**Fix:** define the simulator's known universe concretely (e.g. a curated NSE symbol list in
`seed_prices.py`) and have validation consult it, or explicitly state that validation only applies
when Tapetide is active. As written, the spec and the code cannot both be satisfied.

### 3.4 The mock-LLM "add" scenario (§9) is self-contradictory

The mock table requires an "add" to a ticker that is "not already in the watchlist", but the same
section says the ticker "is extracted by matching against the current watchlist/positions tickers
present in the message text." A ticker that is not in the watchlist cannot be matched against the
watchlist, so the add row is unreachable — and the E2E scenario "Add ... a ticker from the
watchlist" (§12) cannot pass.

**Fix:** specify how the mock extracts a *candidate* ticker for the add case — e.g. parse an
uppercase token from the message, or keep a hard-coded small list of "addable" symbols for mock
mode. Also state that the mock's `quantity` is a fixed `1` (it does, in the other rows) and that
extraction is exact-match, not fuzzy.

### 3.5 §13 refers to a review that does not exist

§13 is titled "Review Notes (doc review pass — resolved)" and opens "Decisions made in response to
the review above," but there is no review above it — and no `REVIEW.md` exists in `planning/`
(this document is the first). Either the referenced review was never committed, or the section is
a vestige of an earlier draft. **Fix:** delete §13 or fold its seven decisions into the sections
they affect and remove the dangling reference. (Note: §13 point 7 duplicates §8's error-shape
requirement, and point 3 duplicates §6/§8, so this is mild redundancy too.)

---

## 4. Specification gaps and ambiguities (non-blocking, but should be pinned down)

1. **Tapetide symbol lookup is assumed, not verified (§6).** The plan says validation uses "a
   Tapetide symbol lookup when Tapetide is active," but the only Tapetide capability it documents
   is the `get_batch_quotes` tool. Whether Tapetide exposes a symbol-search tool is unstated and
   unverified. Confirm against the MCP server before relying on it; otherwise an unknown symbol
   simply returns no quote, which is a different (and simple) validation signal.

2. **The 400-calls/day budget is tighter than §6 implies.** At one call every 2 s, that is 30
   calls/min, so 400 calls is ~13.3 minutes of polling — about **2.6 five-minute sessions**, not
   "a few runs per day." State the practical ceiling (or default the interval lower) so a demo
   does not silently exhaust the daily cap mid-session.

3. **SEBI disclaimer (§6) needs a canonical string and a delivery point.** The requirement is
   stated but no exact text, no format, and no UI element is named. For it to be testable, define
   the exact disclaimer text and where it appears (e.g. appended to AI chat `message` when the
   response was derived from Tapetide data). Note that in practice most demo runs will fall
   outside NSE hours and never use Tapetide, so the disclaimer path is rarely exercised.

4. **`.env.example` is referenced but absent.** §4 says ".env.example committed" and §5 implies it;
   `ls` confirms no `.env.example` exists in the repo. Either add it or drop the reference.

5. **Directory structure (§4) omits real directories.** `.github/` (exists, with CI workflows) and
   the future `backend/app/main.py` (referenced in §11) are not shown. Minor, but the structure
   block is presented as the contract.

6. **Treemap has no library.** §10 names "Lightweight Charts or Recharts," but neither ships a
   treemap/heatmap component, and the heatmap is a first-class feature (§2, §10). Name a library
   (e.g. `d3-hierarchy`/`recharts` `Treemap`, or a dedicated component) so the frontend agent does
   not improvise.

7. **`trades` is write-only.** The schema (§7) logs every trade, but no endpoint (§8) or UI
   surface (§10) reads it back. Either expose it (`GET /api/portfolio/trades`) or state that it is
   an audit log with no consumer.

8. **`portfolio_snapshots` growth is unbounded (§7).** A snapshot every 30 s plus one per trade,
   with no pruning, grows without limit across runs (the DB persists). State a retention policy
   (e.g. cap to last N, or downsample) or explicitly accept unbounded growth for a demo.

9. **NSE-hours check ignores timezone and holidays (§5, §6).** "9:15am-3:30pm IST, Mon-Fri" needs
   the server's timezone handled explicitly (the backend may run in any local TZ) and ideally NSE
   holidays; otherwise "real data" may be selected on a holiday when quotes do not move.

10. **SPA routing / static-export fallback is unspecified (§3, §11).** FastAPI serving a Next.js
    static export needs a catch-all that returns `index.html` for client-side routes. Not
    mentioned; a frontend agent may ship a build that 404s on refresh.

11. **Fractional shares vs. the trade bar (§2, §7, §10).** The schema says "fractional shares
    supported," but §10's trade bar is described only as a "quantity field." State whether the
    quantity input is integer-only or accepts decimals, and whether the API enforces a minimum.

12. **§10 mixes two local-trade conventions.** §9's mock always trades `quantity: 1` while §2/§10
    imply arbitrary user-entered quantities; fine, but the mock's fixed-1 is worth stating as a
    deliberate test simplification (it partly is, in §9).

---

## 5. Consistency nits

- §2 says ten default NSE tickers; §7 lists exactly ten — consistent (good).
- Cash is `1,000,000.0` in §7 and "Rs 10,00,000" in §2 — consistent.
- §13 point 1 ("Money as `REAL`") and point 4 ("SQLite concurrent writes") are decisions with no
  corresponding text in the body; if §13 is removed, be sure those two decisions are not silently
  lost (money type is visible in §7; the concurrency assumption is nowhere else stated).
- §11's launch line names `app.main:app`, but `backend/app/` currently contains only `__init__.py`
  and `market/`. Expected for an unbuilt module, but worth an explicit "to be created" marker so
  agents do not assume it exists.

---

## 6. Recommended next steps

1. **Decide 3.1** (Tapetide vs. Massive) — this gates everything else.
2. Align `README.md`, `backend/CLAUDE.md`, and `MARKET_DATA_SUMMARY.md` with the decision (3.2).
3. Define the simulator's known universe, or scope validation to Tapetide only (3.3).
4. Fix the mock-LLM extraction rule for the "add" case (3.4).
5. Remove or resolve §13 and fold its live decisions into the body (3.5).
6. Sweep the §4 gap list: `.env.example`, Tapetide symbol lookup, budget math, SEBI text, treemap
   library, trade-history endpoint, snapshot retention, TZ/holidays, SPA fallback, quantity type.
