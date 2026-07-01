#!/bin/bash
# deploy/run.sh — Deploy mushin from main branch
# Called by GitHub Actions via SSH or manually on the server.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

# ── Project config — edit these for your project ──────────────────────
APP_DIR="/opt/mushin/mushin"
SERVICE="mushin"
PORT=8013
HEALTH_PATH="/health"
HEALTH_TIMEOUT=10
HEALTH_RETRIES=5
TAILWIND_INPUT="app/static/src/input.css"
TAILWIND_OUTPUT="app/static/style.css"
# ──────────────────────────────────────────────────────────────────────

cd "$APP_DIR"
echo "=== Deploying $SERVICE ==="

# 1. Sync to remote main
#
# Uses `sg` to activate the mushin group for the wrapped command.
# Without this, git's writes inside .git/objects/ can land as deploy:deploy
# (despite the setgid bit on the repo dir), and the service user can't read
# them.
#
# Uses `git reset --hard` rather than `git pull` — if the server's state
# diverged for any reason, reset wins; source of truth is origin/main.
echo "[1/6] Syncing to origin/main..."
sg "$SERVICE" -c "git fetch origin main && git reset --hard origin/main"

# 2. Install/update dependencies
echo "[2/6] Syncing dependencies..."
uv sync --frozen --no-dev

# 3. Build Tailwind CSS (skip if no input.css — not all projects use Tailwind)
echo "[3/6] Building assets..."
if [[ -f "$TAILWIND_INPUT" ]]; then
    if ! command -v tailwindcss &> /dev/null; then
        echo "  tailwindcss not found — installing standalone CLI..."
        ARCH=$(uname -m)
        case "$ARCH" in
            aarch64|arm64) TW_ARCH="linux-arm64" ;;
            x86_64)        TW_ARCH="linux-x64" ;;
            *)             echo "FATAL: Unsupported architecture $ARCH"; exit 1 ;;
        esac
        TW_VERSION="v4.2.2"
        mkdir -p "$HOME/.local/bin"
        curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/download/${TW_VERSION}/tailwindcss-${TW_ARCH}" \
            -o "$HOME/.local/bin/tailwindcss"
        chmod +x "$HOME/.local/bin/tailwindcss"
        echo "  Installed tailwindcss $(tailwindcss --version 2>&1 | head -1)"
    fi
    tailwindcss -i "$TAILWIND_INPUT" -o "$TAILWIND_OUTPUT" --minify
    if [[ ! -f "$TAILWIND_OUTPUT" ]]; then
        echo "FATAL: Tailwind build produced no output"
        exit 1
    fi
else
    echo "  No Tailwind input at $TAILWIND_INPUT — skipping asset build"
fi

# 4. Sync Caddy config (if changed)
echo "[4/6] Checking Caddy config..."
CADDY_SRC="infra/${SERVICE}.caddy"
CADDY_DST="/etc/caddy/conf.d/${SERVICE}.caddy"
if [[ -f "$CADDY_SRC" ]] && ! diff -q "$CADDY_SRC" "$CADDY_DST" &>/dev/null; then
    echo "  Caddy config changed — copying and reloading..."
    sudo cp "$CADDY_SRC" "$CADDY_DST"
    sudo systemctl reload caddy
    echo "  Caddy reloaded."
else
    echo "  Caddy config unchanged or missing — skipping."
fi

# 5. Restart the application service
echo "[5/6] Restarting $SERVICE service..."
sudo systemctl restart "$SERVICE"

# 6. Health check
echo "[6/6] Running health check..."
attempt=0
while [[ $attempt -lt $HEALTH_RETRIES ]]; do
    attempt=$((attempt + 1))
    sleep 2
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$HEALTH_TIMEOUT" \
        "http://127.0.0.1:$PORT$HEALTH_PATH" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        echo "Health check passed (HTTP $http_code) on attempt $attempt."
        echo "=== Deploy successful ==="
        exit 0
    fi
    echo "  Attempt $attempt/$HEALTH_RETRIES: HTTP $http_code (waiting...)"
done

echo "=== Deploy FAILED — health check did not return 200 ==="
echo "Diagnostics:"
echo "  systemctl status $SERVICE"
echo "  journalctl -u $SERVICE -n 50 --no-pager"
systemctl status "$SERVICE" --no-pager || true
exit 1
