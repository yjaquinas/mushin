#!/bin/bash
# run.sh — local development entry point
# Starts the Tailwind watcher (if input.css exists) and uvicorn with --reload.
set -euo pipefail

cd "$(dirname "$0")"

TAILWIND_INPUT="app/static/src/input.css"
TAILWIND_OUTPUT="app/static/style.css"

# Start Tailwind watcher in background (skip if no input.css)
if [[ -f "$TAILWIND_INPUT" ]]; then
    tailwindcss --input "$TAILWIND_INPUT" --output "$TAILWIND_OUTPUT" --watch &
    TW_PID=$!
    trap 'kill $TW_PID 2>/dev/null' EXIT
    echo "Tailwind watcher running (pid=$TW_PID)"
fi

# Start the FastAPI dev server with auto-reload on :8000
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
