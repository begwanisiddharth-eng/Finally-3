# FinAlly E2E Tests (Playwright)

Playwright E2E suite (PLAN.md section 12) run against the full local app: the FastAPI
backend serving the Next.js static export. No Docker.

## Prerequisites

- `frontend/out/` built (`cd frontend && npm run build`).
- Backend deps synced (`cd backend && uv sync`).
- `uv` and Node LTS on PATH.

## Run

```bash
cd test
npm install
npx playwright install chromium   # once
npm test
```

The Playwright `webServer` fixture launches an isolated backend itself:
`LLM_MOCK=true`, `MARKET_DATA_SOURCE=simulator`, a per-run `DATABASE_PATH` under
`test/.e2e/`, on port **8200** (never the user's 8000 or `db/finally.db`). Each run
uses a fresh DB file, so the seeded state (10-ticker watchlist, Rs 10 lakh) is
deterministic. Tests run serially (`workers: 1`) against the one instance.

## Scenarios (section 12)

1. `01-fresh-start` — default 10-ticker watchlist, Rs 10 lakh cash, prices streaming.
2. `02-watchlist` — add (WIPRO) and remove a ticker.
3. `03-buy` — buy decreases cash, position appears, totals update.
4. `04-sell` — sell increases cash, position disappears when sold to zero.
5. `05-visualization` — heatmap renders tinted cells, P&L chart has data.
6. `06-chat` — mocked AI "buy 1 INFY" executes inline and portfolio refetches.
7. `07-sse-resilience` — prices keep updating over time.
