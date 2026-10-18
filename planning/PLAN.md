# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single start script (no Docker, no containers). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default NSE tickers with live-updating prices in a grid
- Rs 10,00,000 (10 lakh) in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~250ms via CSS transitions — deliberately shorter than the simulator's ~500ms tick interval (§6), so each flash fully fades before the next tick instead of overlapping into a near-permanent tint
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Process, Single Port (No Docker)

```
┌─────────────────────────────────────────────────┐
│  Local Process (port 8000)                       │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (local file)                   │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, created directly on the local filesystem
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → Groq (`groq/openai/gpt-oss-120b`), with structured outputs for trade execution
- **Market data**: Environment-variable driven, re-evaluated continuously, not just at startup — simulator by default; real Indian market data via the Tapetide MCP server during NSE trading hours if an API key is provided. A background supervisor hands the app over between the two sources as trading hours start/end mid-session (§6).
- **No containerization**: everything runs as native local processes (`uv run` for the backend, a static build for the frontend) started by a single script — no Docker, no docker-compose, no image builds

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| No Docker | Avoids container runtime as a dependency; a single start script runs the backend and serves the prebuilt frontend directly on the host |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

This is the **target** layout. As of this revision, only `.github/`, `backend/app/market/`
(market data) and its tests exist; `frontend/`, `scripts/`, `test/`, `db/`, `backend/db/`, and
`backend/app/main.py` are not yet built — an agent should not assume any path below exists until
it has checked.

```
finally/
├── .github/                  # CI workflows [exists]
├── frontend/                 # Next.js TypeScript project (static export) [target]
├── backend/                  # FastAPI uv project (Python) [partially exists — see below]
│   ├── app/
│   │   ├── market/            # Market data subsystem [exists, complete]
│   │   └── main.py            # FastAPI entrypoint [target — not yet created, see §11]
│   └── db/                   # Schema definitions, seed data, migration logic [target]
├── planning/                 # Project-wide documentation for agents [exists]
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/                  # [target]
│   ├── start_mac.sh          # Build frontend, launch backend (macOS/Linux)
│   ├── stop_mac.sh           # Stop the running backend process (macOS/Linux)
│   ├── start_windows.ps1     # Build frontend, launch backend (Windows PowerShell)
│   └── stop_windows.ps1      # Stop the running backend process (Windows PowerShell)
├── test/                     # Playwright E2E tests [target]
├── db/                       # SQLite file lives here at runtime [target]
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── .env                      # Environment variables (gitignored, .env.example committed) [exists]
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic for *database rows* — the default user profile, the 10 default watchlist entries (§7). This is distinct from `backend/app/market/seed_prices.py`, which seeds *market simulator state* (starting prices, GBM params, the NSE symbol validation list) and is never touched by database initialization. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is where the SQLite file (`db/finally.db`) is created by the backend and persists across process restarts (plain local file, no volume machinery needed).
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests, run against a locally started instance of the app. Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that build the frontend once and launch/stop the backend process directly on the host.

---

## 5. Environment Variables

```bash
# Required unless LLM_MOCK=true: Groq API key for LLM chat functionality
GROQ_API_KEY=your-groq-api-key-here

# Optional: Tapetide MCP bearer token for real Indian (NSE) market data
# If not set, the built-in market simulator is used (recommended for most users)
TAPETIDE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `TAPETIDE_API_KEY` is set and non-empty, AND the current time is within NSE trading hours (9:15am-3:30pm IST, Mon-Fri) → backend polls Tapetide for real market data. The check converts the server's local time to IST explicitly (the server may run in any timezone) and is a weekday/clock-time approximation only — it does not account for NSE holidays, so a market holiday that falls on a weekday is still treated as trading hours (Tapetide simply won't show price movement that day).
- Otherwise (no key, or outside NSE trading hours) → backend uses the built-in market simulator, seeded from the last known real close price when available
- **This is not a one-time decision at startup.** A background supervisor re-evaluates it continuously (every ~60s) and hands the app over between sources the moment the condition changes — e.g. a session started during trading hours keeps running on Tapetide until 3:30pm and then falls over to the simulator automatically, and a session started outside trading hours picks up Tapetide the moment the market opens, without a restart. See §6, "Live Handover."
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend loads `.env` from the project root itself at startup, via `python-dotenv`'s `load_dotenv()` called at the top of `app/main.py` (not via a container `--env-file` or a shell-level export) — this is a direct dependency of the backend (`pyproject.toml`), not something agents may skip

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Tapetide client implement the same abstract interface
(`MarketDataSource`: `start`/`stop`/`add_ticker`/`remove_ticker`/`get_tickers`/`validate_ticker`).
A `MarketDataManager` owns whichever one is currently active and is the only thing downstream code
(API routes, SSE streaming) depends on — never a concrete source directly. All downstream code is
therefore agnostic not just to *which* source is active, but to the fact that it can change.

### Simulator (Default, and Fallback Outside NSE Hours)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., bank stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices for the default NSE watchlist (e.g., HDFCBANK ~Rs 1,700, INFY ~Rs 1,900, etc.); when a real Tapetide quote has been seen for a ticker, the simulator seeds from that last real close instead
- Runs as an in-process background task — no external dependencies
- Used whenever `TAPETIDE_API_KEY` is unset, or the current time is outside NSE trading hours (9:15am-3:30pm IST, Mon-Fri) — Tapetide quotes don't move at all outside those hours, so the simulator keeps the demo lively any time it's run

### Tapetide (Optional, Real NSE Data During Trading Hours)

- Tapetide (`https://mcp.tapetide.com/mcp`) is an **MCP server**, not a plain REST API — it has no separate HTTP/REST endpoint of its own. The backend therefore acts as a minimal MCP client itself: it opens an MCP streamable-HTTP connection to that URL, authenticated with a `Bearer` token (`TAPETIDE_API_KEY`), and calls the `get_batch_quotes` tool directly — no interactive/chat MCP usage, just a programmatic tool call from a background task
- Use the latest official MCP Python SDK (`mcp` package) for the client; `uv add mcp`. The SDK's streamable-HTTP transport is built on `httpx2` (the `httpx`/`httpx-sse` successor), which is also a direct dependency (`uv add httpx2`) since the client builds its own `httpx2.AsyncClient` to attach the Bearer auth header.
- Polls `get_batch_quotes` with the full watchlist (up to 20 symbols per call; the 10-ticker default watchlist fits in one call) every 2 seconds
- The user's Tapetide plan is capped at 400 calls/day. At 1 call every 2 seconds, that's 30 calls/minute, so 400 calls is only **~13 minutes of continuous polling** — roughly 2-3 five-minute demo sessions per day, not "a few runs per day." The polling interval is a backend config constant, not something the frontend controls, so it's easy to raise (reducing call frequency) if the daily cap is at risk; the project owner is expected to run short, deliberate demo sessions rather than leave Tapetide polling running continuously.
- Parses the MCP tool response into the same format as the simulator (ticker, price, previous price, timestamp)
- SEBI disclaimer requirement: any AI chat response that includes commentary, analysis, buy/hold/sell suggestions, or portfolio advice derived from Tapetide data must append this exact text to the `message` field: *"Disclaimer: This is not financial advice. I am not a SEBI-registered research analyst or investment advisor. Please consult a qualified financial advisor before making any investment decisions."* Plain quote display (watchlist prices, charts) and watchlist operations do not require it. In practice, most demo runs happen outside NSE hours and never touch Tapetide, so this path is rarely exercised — but the system prompt in §9 must still instruct the LLM to include it whenever applicable.
- No hard cap on watchlist size is enforced in code. If the watchlist grows past 20 tickers, the backend simply issues multiple `get_batch_quotes` calls per poll cycle (more daily-call budget consumed, no functional change). The demo is expected to be run by the project owner, who will keep the watchlist at 15 tickers or fewer.

### Live Handover

Source selection is not a one-time decision made once at process startup — a background
supervisor task re-checks the `TAPETIDE_API_KEY` + NSE-trading-hours condition every ~60 seconds
and hands the app over to the other source the moment the desired one changes. This happens via
`MarketDataManager`, which owns the active `MarketDataSource` and is itself what the rest of the
backend depends on:

- **Who triggers it**: `MarketDataManager`'s own supervisor task, not an external caller.
- **How the new source inherits state**: the manager starts the new source with the *same ticker
  list* the old one was tracking (`get_tickers()`), then stops the old one. On a Tapetide →
  simulator handover, the simulator's existing "seed from the cache's last known price" behavior
  (above) means it picks up the real prices Tapetide left behind — this is the case that makes
  that seeding behavior reachable; a cold start with no prior Tapetide session in this process has
  nothing to seed from, and uses the static `SEED_PRICES` table instead.
- **Why the SSE stream is unaffected**: the shared `PriceCache` is never replaced or recreated
  during a handover — only the writer feeding it changes. SSE clients read from the cache, not
  from a source reference, so they see no gap or reset.

### Tracked Tickers = Watchlist ∪ Held Positions

The set of tickers actively priced is **not** just the watchlist — it's the union of the
watchlist and every ticker currently held in a position. Removing a ticker from the watchlist
(§8 `DELETE /api/watchlist/{ticker}`) removes it from the watchlist *table*, but the backend only
calls `MarketDataManager.remove_ticker()` (stopping its price updates) if that ticker is not also
held in a position. A held-but-unwatched ticker keeps a live price so `GET /api/portfolio`'s
unrealized P&L (§8) stays correct; it just no longer appears in the watchlist panel (§10). The
reverse direction already falls out naturally: buying a ticker not yet tracked requires it to be
on the watchlist first (§8, trade validation), so a newly-held position is always already tracked.

### Ticker Validation

- Adding a ticker (manually via `POST /api/watchlist` or via the AI's `watchlist_changes`) is validated against the active market data source via `MarketDataSource.validate_ticker(ticker)`:
  - **Tapetide active**: a single-symbol `get_batch_quotes` call is the validation signal — the response's `found: false` field means the ticker doesn't exist. No separate symbol-lookup tool is needed.
  - **Simulator active**: the simulator has no real backing universe (it would otherwise seed *any* string with a random price), so validation instead checks a curated, static list of recognized NSE symbols (`NSE_SYMBOL_UNIVERSE` in `backend/app/market/seed_prices.py`).
- If the ticker is not recognized, the add is rejected and no watchlist row is created. The API returns an error the frontend surfaces as a flashed message to the user (e.g. "No stock with ticker XYZ exists"); when the AI attempts this via `watchlist_changes`, the same error is returned in the chat response so the LLM can relay it to the user.

### Shared Price Cache

- A single background task (simulator or Tapetide poller) writes to an in-memory price cache
- The cache holds, per ticker: the latest price, the previous *tick's* price (for the up/down flash), the session/day baseline price (`previous_close` — see below), and a timestamp
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### Daily Change % vs. Tick-over-Tick Change

The watchlist's "daily change %" (§2, §10) and the flash-on-update color (§2) are two different
baselines, both carried on the same cache entry:

- **Tick-over-tick** (`change`, `change_percent`, `direction`): computed against the *previous
  update* (~500ms under the simulator, ~2s under Tapetide). Drives the green/red flash.
- **Day baseline** (`day_change`, `day_change_percent`, computed against `previous_close`): under
  Tapetide, `previous_close` is the exchange's real previous close, returned directly by
  `get_batch_quotes`. Under the simulator — which has no real "yesterday" to reference —
  `previous_close` is the price the ticker's current simulated session started at, so the
  watchlist's "daily change %" reads as "change since this simulator session began" rather than a
  literal exchange-day change. This is a deliberate approximation, not a bug: a GBM demo has no
  real previous trading day to compare against.

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes the **entire current price map** (every tracked ticker, not just the one that
  moved) only when the cache actually changes, checked at a ~500ms poll cadence — in practice this
  means the stream updates at ~500ms intervals under the simulator, and at the Tapetide poll
  cadence (~2s) when Tapetide is the active source, since that's how often the cache is actually
  written. There is no synthetic re-emission to force a 500ms cadence under Tapetide — the numbers
  don't change between real polls, so holding the UI steady for ~2s is simpler than faking motion.
- Each ticker's entry in that map contains price, previous price, previous close, timestamp,
  tick-over-tick change/direction, and day change (see `PriceUpdate.to_dict()`)
- `GET /api/watchlist` (§8) also returns "latest prices," overlapping with the SSE feed. `GET /api/watchlist` is authoritative for the very first render (before the `EventSource` connection has delivered its first frame); once SSE delivers its first frame, the stream is authoritative and the frontend doesn't need to re-poll `GET /api/watchlist` for prices.
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- A fresh `db/` directory (e.g. on first run, or after deleting `finally.db`) starts with a clean, seeded database automatically

Accessed via `aiosqlite`, not raw `sqlite3` or an ORM — the backend is async FastAPI with
concurrent background writers (the price-cache task, the 30-second snapshot task, trade-handling
requests), so a synchronous driver would block the event loop; an ORM (SQLAlchemy et al.) is
unwarranted weight for five small tables and simple queries.

Every `TEXT` timestamp column in this schema (`created_at`, `added_at`, `updated_at`,
`executed_at`, `recorded_at`) is stored as **UTC ISO-8601** (e.g. `2026-10-19T09:15:00+00:00`),
regardless of the server's local timezone — this is distinct from the NSE-trading-hours check
(§5), which explicitly converts to IST for that one comparison and does not affect how timestamps
are stored. The frontend converts to local time for display.

### Schema

All tables include a `user_id` column defaulting to `"default"`, **except `users_profile`**, whose primary key *is* the user id (`id`, not a separate `user_id` column) since one row is already scoped to one user by definition. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `1000000.0`, i.e. Rs 10 lakh)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`
- `avg_cost` only changes on a **buy** (new weighted average: `(old_qty * old_avg_cost + buy_qty * buy_price) / (old_qty + buy_qty)`). A **sell** reduces `quantity` and leaves `avg_cost` unchanged — it is the cost basis for whatever's left, not a running average that should move just because shares were sold. Realized P&L on a sell is `(sell_price - avg_cost) * sell_qty`, logged implicitly via the `trades` row (price vs. the position's `avg_cost` at the time); it is not separately stored. If a sell brings `quantity` to 0, the position row is deleted rather than kept at zero.

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, immediately after each trade execution, **and once at app startup** (first valuation of cash + any existing positions) — the startup snapshot exists specifically so the P&L chart has at least one point before 30 seconds have passed or any trade has happened; without it, §12's "P&L chart has data points" E2E check would be flaky on a fresh app start. No retention/pruning policy — rows accumulate indefinitely across restarts. Accepted as unbounded growth: a demo-length `db/finally.db` (hours to a few days of use) stays small (a few thousand rows at most), and adding pruning is unwarranted complexity for this app's lifetime.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=1000000.0` (Rs 10 lakh)
- Ten watchlist entries (NSE symbols): HEROMOTOCO, BEL, PIDILITIND, LTF, HDFCBANK, INFY, RELIANCE, TCS, ICICIBANK, TATAMOTORS

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |
| GET | `/api/portfolio/trades` | Trade history log (ticker, side, quantity, price, executed_at), most recent first |

Trade validation failures (insufficient cash on buy, insufficient shares on sell, untracked ticker) return HTTP 400 with body `{"error": "<human-readable message>"}`. This shape is required for both the manual trade endpoint and the trade-validation path used when the AI auto-executes trades in chat.

**A trade requires the ticker to be currently tracked** — present in the price cache, i.e. on the
watchlist or already held in a position (§6, "Tracked Tickers"). A trade naming any other ticker
is rejected (not auto-added to the watchlist) with: *"Only tickers in your watchlist or held in
your portfolio can be traded. Add `<TICKER>` to your watchlist first."* This applies identically
to the manual trade bar and to AI-initiated trades in chat — the LLM relays the same message back
to the user rather than silently adding the ticker itself.

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

`POST /api/watchlist` returns HTTP 400 with `{"error": "<human-readable message>"}` if the ticker isn't recognized by the active market data source (see Ticker Validation in §6).

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |
| GET | `/api/chat/history` | Last 20 `chat_messages` rows (role, content, actions, created_at), oldest first |

- `POST /api/chat` request body: `{"message": "<user's text>"}`. The backend loads prior turns
  itself from `chat_messages` (§9 step 2) — the client never echoes conversation history back.
- `POST /api/chat` failure path: if Groq times out, errors, or returns a response that doesn't
  parse as the structured schema (§9), the endpoint returns HTTP 502 with
  `{"error": "<human-readable message>"}` (distinct from the 400 trade/watchlist validation shape,
  since this is an upstream failure, not a client input error) — no `chat_messages` row is written
  for a call that failed this way. The frontend's loading indicator (§10) resolves to showing this
  error inline in the chat panel rather than a silent failure.
- The chat panel is not session-only: the frontend loads `/api/chat/history` on mount to
  repopulate the conversation after a page reload, rather than showing an empty panel while the
  LLM (which already has this history via §9 step 2) silently "remembers" turns the user can no
  longer see.

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (used by start scripts to confirm the backend is ready) |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use the groq-skill to call LiteLLM directly against Groq, using the `groq/openai/gpt-oss-120b` model. Structured Outputs should be used to interpret the results.

There is a GROQ_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context: cash, positions with P&L, watchlist with live prices, total portfolio value, and `data_source` (`"tapetide"` or `"simulator"` — `MarketDataManager.active_source_name`, §6). The LLM needs this last field to decide whether the SEBI disclaimer applies (below); without it, there is no way for the model to tell which source the prices it's reasoning about came from.
2. Loads the last 20 rows of conversation history from the `chat_messages` table (same window `GET /api/chat/history`, §8, exposes to the frontend — one number, stated once, used by both)
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → Groq, requesting structured output, using the groq-skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Groq inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "HDFCBANK", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "WIPRO", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON
- Append the exact SEBI disclaimer text (§6) to `message` whenever the response includes commentary, analysis, or a buy/hold/sell suggestion, **and** the portfolio context's `data_source` field (§9 step 1) is `"tapetide"`. When `data_source` is `"simulator"`, never append it — the data isn't real, so the disclaimer's premise doesn't apply.

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling Groq. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

Mock logic is a minimal keyword match on the incoming message (case-insensitive substring), checked in order, first match wins:

| Message contains | Mock response |
|---|---|
| `"buy"` + a ticker already in the watchlist | `message` confirms the buy; `trades: [{ticker, side: "buy", quantity: 1}]` |
| `"sell"` + a ticker currently held in positions | `message` confirms the sell; `trades: [{ticker, side: "sell", quantity: 1}]` |
| `"add"` + an uppercase token not already in the watchlist | `message` confirms the addition; `watchlist_changes: [{ticker, action: "add"}]` |
| `"remove"` + a ticker in the watchlist | `message` confirms the removal; `watchlist_changes: [{ticker, action: "remove"}]` |
| anything else | `message` is a canned "Here's your portfolio summary" string; no `trades`, no `watchlist_changes` |

Ticker extraction scans *all* all-caps alphanumeric tokens (2+ chars) in the message — not just the
first — and takes the first one that satisfies the row's condition, skipping the reserved verb
tokens `BUY`, `SELL`, `ADD`, `REMOVE` themselves (so "BUY HDFCBANK" doesn't try to match `BUY` as a
ticker and give up). Exact-match, not fuzzy:
- **buy**: first non-verb token that is a current watchlist ticker. No match → falls through to "anything else".
- **sell**: first non-verb token that is a current position's ticker. No match → falls through to "anything else".
- **add**: first non-verb token that is *not* already in the watchlist — this is what lets the mock "add WIPRO" scenario work even though WIPRO was never seen before. No such token → falls through to "anything else".
- **remove**: first non-verb token that is a current watchlist ticker (same condition as buy).

`quantity` is always a fixed `1` for mock trades — a deliberate test simplification, not a general mock capability. This table covers exactly the E2E scenarios in §12 (trade execution inline, watchlist add/remove) — it is intentionally not a general-purpose mock LLM.

The "add" extraction is deliberately naive — it takes *any* non-verb all-caps token, not just real
symbols, so a mock message like "ADD SOME IDEA" would propose `watchlist_changes: [{ticker:
"SOME", action: "add"}]`. This is harmless: the proposed ticker still goes through the same
`validate_ticker` check (§6) as any other add, so an unrecognized token like `SOME` gets rejected
there, not here. E2E tests for the add scenario must still use a real symbol (e.g. WIPRO) to
observe a successful add.

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on tick-over-tick change, §6), daily change % (`day_change_percent` from the SSE payload, §6 — under the simulator this reads as change since the current demo session started, not a literal exchange-day change), and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here. **Explicitly live-since-load, not historical**: there is no price-history endpoint or backing storage (a deliberate scope decision — see §13), so this chart uses the same SSE-accumulated buffer as that ticker's sparkline, just rendered larger. It starts empty on every page load and for any ticker just added, filling in as ticks arrive; it is not expected to show pre-load history.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill. The quantity field accepts decimal input (schema supports fractional shares, §7); the API rejects a quantity that is zero or negative with the standard `400` error shape (§8).
- **AI chat panel** — docked/collapsible sidebar. Loads prior messages from `GET /api/chat/history` on mount (§8), so a page reload doesn't show an empty panel. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Two charting libraries, each used for what it's good at: **Lightweight Charts** for the time-series charts (sparklines, main chart, P&L chart) — canvas-based, built for financial time series; **Recharts' `Treemap`** component (built on `d3-hierarchy` internally) for the portfolio heatmap (§2), since Lightweight Charts has no treemap primitive. This is a deliberate two-library split, not an either/or choice left to the Frontend Engineer.
- Price flash effect: on receiving a new price, briefly apply a CSS class with a ~250ms background color transition, then remove it (§2 — shorter than the ~500ms simulator tick so flashes don't overlap)
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Running Locally (No Docker)

### Build & Run Steps

```
1. Frontend build (once, or whenever frontend code changes):
   cd frontend && npm install && npm run build
   (produces a static export at frontend/out/, per Next.js's output: 'export' default)

2. Backend dependencies:
   cd backend && uv sync   (installs Python dependencies from lockfile)

3. Launch (from inside backend/ — app.main resolves relative to backend/, not the repo root):
   cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   (FastAPI serves frontend/out/ as static files AND all /api/* routes on port 8000)
```

Binds to `127.0.0.1`, not `0.0.0.0` — this is a local-only, auth-free app (§2, §11), so it should not be reachable from other machines on the LAN by default.

`backend/app/main.py` does not exist yet — it is the FastAPI entrypoint to be created, wiring together the market data factory, API routers, and static file serving. It mounts `frontend/out/` as the static file root and calls `load_dotenv()` (§5) before reading any environment variable.

The frontend is a single-page application with no client-side routing (§10) — there is exactly one HTML entry point (`index.html`). FastAPI's static file mount therefore needs no SPA catch-all/fallback route; only `/` needs to resolve to `index.html`, and everything else is `/api/*`.

No container runtime, no image build, no volume mounts — the backend reads `.env` and writes `db/finally.db` directly on the host filesystem.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the frontend static export if not already built (or if `--build` flag passed)
- Runs `uv sync` in `backend/`
- Launches `uvicorn` as a background process, recording its PID to a local file (e.g. `.finally.pid`)
- Polls `/api/health` until ready, then prints the URL and optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Reads the PID file and stops the running `uvicorn` process
- Does NOT delete `db/finally.db` (data persists across runs)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows (using `Start-Process`/`Stop-Process` and the same PID-file approach).

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

Cloud/container deployment (AWS App Runner, Render, etc.) is explicitly out of scope for this build — the project targets local-only execution via the start scripts above.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Tapetide MCP response parsing works, NSE-trading-hours gating selects the right source, both implementations conform to the abstract interface, `MarketDataManager` hands over between sources in both directions without losing tracked tickers or interrupting the shared cache
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: Playwright tests run directly against a locally started instance of the app (via the start script), with no Docker/Playwright containers involved.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, Rs 10 lakh balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Design Decisions Log

Standing decisions, settled during doc review passes, that aren't self-evident from the sections
above. Kept here, in the plan itself, rather than as a pointer into `planning/REVIEW.md` — that
file is regenerated by each review pass and its section numbers shift, so a cross-reference into
it goes stale; a decision worth keeping belongs in the plan, not behind an external citation.

- **Money is stored as `REAL` (float)**, not fixed-point/cents. Accepted float drift as fine for
  this simulated/demo app rather than rounding to paise on write.
- **SQLite concurrent writes are not specially handled.** The price-cache task, the 30-second
  snapshot task, and trade-handling requests all touch SQLite, but expected trade volume (3-4/min
  at most) makes lock contention a non-issue in practice.
- **No dev-mode / hot-reload workflow is specified for the frontend** — only the build-and-serve
  flow in §11. Agents build and check against the static export, not `next dev`.
- **Multi-user `user_id` scaffolding (§7) is kept** even though multi-user is out of scope — a
  deliberate choice, not default scaffolding creep.
- **Simulator realism (correlated GBM + random events, §6) is kept** as wanted complexity/polish,
  not simplified to independent per-ticker GBM.
- **No synthetic 500ms re-emission under Tapetide (§6)** — the stream genuinely runs at the poll
  cadence (~2s) when Tapetide is active, rather than adding a timer to fake a steady 500ms cadence
  with unchanged numbers. Dropped as complexity with no real payoff, not implemented.
- **The main chart has no price-history endpoint or backing storage (§10)** — it is explicitly
  live-since-load, the same SSE-accumulated buffer as the sparkline just rendered larger, and
  starts empty on every page load. Accepted as a scope boundary rather than adding a history table
  or ring buffer and a new endpoint to back a "real" historical chart.
