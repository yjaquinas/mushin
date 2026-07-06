#!/bin/bash
# run.sh — local development entry point
# Starts the Tailwind watcher (if input.css exists) and uvicorn with --reload.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# Check port before starting anything, loop until resolved
while true; do
    if ! ss -tlnp "sport = :$PORT" | grep -q LISTEN; then
        break
    fi
    pid=$(ss -tlnp "sport = :$PORT" | grep LISTEN | sed -E 's/.*pid=([0-9]+).*/\1/')
    proc_info=$(ss -tlnp "sport = :$PORT" | grep LISTEN | sed -E 's/.*users:\(\((.*)\)\)/\1/')
    cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "unknown")
    echo "Port $PORT is already in use by: $proc_info"
    echo "  Command: $cmd"
    echo ""
    echo "What would you like to do?"
    echo "  1) Kill the process and restart on port $PORT"
    echo "  2) Try next port ($((PORT + 1)))"
    echo "  3) Quit"
    read -r choice
    if [[ "$choice" == "1" ]]; then
        kill "$pid" 2>/dev/null && echo "Killed process $pid"
        sleep 1
        break
    elif [[ "$choice" == "2" ]]; then
        PORT=$((PORT + 1))
        # keep looping to check the new port
    elif [[ "$choice" == "3" ]]; then
        exit 0
    else
        echo "Invalid choice. Exiting."
        exit 1
    fi
done

TAILWIND_INPUT="app/static/src/input.css"
TAILWIND_OUTPUT="app/static/style.css"

# Start Tailwind watcher in background (skip if no input.css)
if [[ -f "$TAILWIND_INPUT" ]]; then
    tailwindcss --input "$TAILWIND_INPUT" --output "$TAILWIND_OUTPUT" --watch=always &
    TW_PID=$!
    trap 'kill $TW_PID 2>/dev/null' EXIT
    echo "Tailwind watcher running (pid=$TW_PID)"
fi

# Start the FastAPI dev server with auto-reload on selected port
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
