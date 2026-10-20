# FinAlly Frontend

Next.js (App Router) static export that is served by the FastAPI backend as static files — see the
root [`README.md`](../README.md) and [`planning/PLAN.md`](../planning/PLAN.md) §10/§11.

Stack: Next.js 16 (`output: 'export'`), React 19, TypeScript (strict), Tailwind CSS v4, Lightweight
Charts v5 for time-series, a self-rendered squarified-treemap heatmap, and native `EventSource` for
the SSE price stream. It talks to the backend only through same-origin `/api/*` endpoints.

## Commands

```bash
npm install
npm run build     # static export to frontend/out/ (what the backend serves)
npm test          # Vitest + React Testing Library unit tests
npm run lint      # ESLint
```

There is **no dev-server workflow** for this project (§13) — build the static export and run it
through the backend (`scripts/start_*`), which serves `frontend/out/` and the `/api/*` routes on one
port. All dynamic data comes from the backend, so `next dev` is not used.
