#!/usr/bin/env bash
# Stop the running FinAlly backend. See PLAN.md section 11.
# Never kills an unrelated PID; never deletes the database.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PID_FILE="${FINALLY_PID_FILE:-$REPO_ROOT/.finally.pid}"

if [ ! -f "$PID_FILE" ]; then
    echo "No PID file; FinAlly is not running."
    exit 0
fi

TARGET_PID="$(cat "$PID_FILE")"
if kill -0 "$TARGET_PID" 2>/dev/null; then
    kill "$TARGET_PID"
    echo "Stopped FinAlly (PID $TARGET_PID)"
else
    echo "PID $TARGET_PID not running (stale PID file)"
fi
rm -f "$PID_FILE"
