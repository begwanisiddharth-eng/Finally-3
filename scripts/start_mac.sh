#!/usr/bin/env bash
# Start the FinAlly backend (and build the frontend if present). See PLAN.md section 11.
# Idempotent: safe to run repeatedly. Pass --build to force a frontend rebuild.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PID_FILE="${FINALLY_PID_FILE:-$REPO_ROOT/.finally.pid}"
PORT="${PORT:-8000}"
FORCE_BUILD=false
for arg in "$@"; do [ "$arg" = "--build" ] && FORCE_BUILD=true; done

# --- .env bootstrap ---
if [ ! -f "$REPO_ROOT/.env" ]; then
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo "Created .env from .env.example"
fi

# --- GROQ_API_KEY check (skipped under LLM_MOCK=true) ---
LLM_MOCK_VAL="$(grep -E '^LLM_MOCK=' "$REPO_ROOT/.env" | cut -d= -f2- || true)"
if [ "$(echo "$LLM_MOCK_VAL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" != "true" ]; then
    GROQ_VAL="$(grep -E '^GROQ_API_KEY=' "$REPO_ROOT/.env" | cut -d= -f2- || true)"
    if [ -z "$GROQ_VAL" ] || [ "$GROQ_VAL" = "your-groq-api-key-here" ]; then
        echo "WARNING: GROQ_API_KEY is not set in .env; chat will fail unless LLM_MOCK=true." >&2
    fi
fi

# --- Already-running check ---
if [ -f "$PID_FILE" ]; then
    EXISTING_PID="$(cat "$PID_FILE")"
    if kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "FinAlly already running (PID $EXISTING_PID) at http://127.0.0.1:$PORT"
        exit 0
    fi
    rm -f "$PID_FILE"  # stale
fi

# --- Frontend build (only if a frontend project exists) ---
FRONTEND="$REPO_ROOT/frontend"
if [ -f "$FRONTEND/package.json" ]; then
    [ -d "$FRONTEND/node_modules" ] || (cd "$FRONTEND" && npm install)
    if [ "$FORCE_BUILD" = true ] || [ ! -d "$FRONTEND/out" ]; then
        (cd "$FRONTEND" && npm run build)
    fi
else
    echo "WARNING: No frontend/ project found; backend will serve the API only." >&2
fi

# --- Backend deps ---
(cd "$REPO_ROOT/backend" && uv sync)

# --- Launch uvicorn directly and record its PID ---
(cd "$REPO_ROOT/backend" && uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT") &
echo $! > "$PID_FILE"

# --- Wait for health ---
for _ in $(seq 1 40); do
    sleep 0.5
    if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
        echo "FinAlly is running at http://127.0.0.1:$PORT (PID $(cat "$PID_FILE"))"
        exit 0
    fi
done
echo "WARNING: Backend did not report healthy in time; check the logs." >&2
exit 1
