#!/usr/bin/env bash
set -euo pipefail

# Rebuilds and restarts the production Mini App frontend from the current repo.
# Intended server usage:
#   /opt/botvpk/scripts/redeploy-miniapp.sh

APP_DIR="${APP_DIR:-/opt/botvpk}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

cd "$APP_DIR"

echo "[miniapp] Pulling latest main..."
git pull --ff-only

BUILD_ID="${BUILD_ID:-$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"
export BUILD_ID

echo "[miniapp] Rebuilding frontend without Docker cache, BUILD_ID=$BUILD_ID..."
docker compose -f "$COMPOSE_FILE" build --no-cache frontend

echo "[miniapp] Restarting frontend and nginx..."
docker compose -f "$COMPOSE_FILE" up -d frontend nginx

echo "[miniapp] Active containers:"
docker compose -f "$COMPOSE_FILE" ps frontend nginx

mini_url=""
if [[ -f "$ENV_FILE" ]]; then
  mini_url="$(grep -E '^MINI_APP_URL=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
fi

if [[ -n "$mini_url" ]]; then
  echo "[miniapp] Version endpoint:"
  curl -fsS "${mini_url%/}/version.json" || true
  echo
else
  echo "[miniapp] MINI_APP_URL not found in $ENV_FILE"
fi

echo "[miniapp] Done. Close and reopen Telegram Mini App after this."
