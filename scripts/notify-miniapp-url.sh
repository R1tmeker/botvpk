#!/usr/bin/env bash
set -euo pipefail

# Detects the current Cloudflare Quick Tunnel URL, updates .env, refreshes the
# bot menu button via Telegram API, restarts the bot container, and notifies admin.
# Defaults are production-friendly for /opt/botvpk, but can be overridden:
#   APP_DIR=/opt/botvpk TELEGRAM_NOTIFY_ID=123 bash scripts/notify-miniapp-url.sh --force

APP_DIR="${APP_DIR:-/opt/botvpk}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
STATE_FILE="${STATE_FILE:-$APP_DIR/.mini_app_url.notified}"
CF_SERVICE="${CF_SERVICE:-vpk-tunnel}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"
COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
FORCE=0
ARG_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    http://*|https://*)
      ARG_URL="$1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

env_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 1
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1
  line="${line#*=}"
  line="${line%$'\r'}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s' "$line"
}

detect_url_once() {
  if [[ -n "$ARG_URL" ]]; then
    printf '%s' "$ARG_URL"
    return 0
  fi

  local url=""
  if command -v journalctl >/dev/null 2>&1; then
    url="$(journalctl -u "$CF_SERVICE" -n 120 --no-pager 2>/dev/null \
      | grep -oE 'https://[a-z0-9-]+[.]trycloudflare[.]com' \
      | tail -n 1 || true)"
  fi

  if [[ -z "$url" && -f /tmp/cf_tunnel.log ]]; then
    url="$(grep -oE 'https://[a-z0-9-]+[.]trycloudflare[.]com' /tmp/cf_tunnel.log \
      | tail -n 1 || true)"
  fi

  printf '%s' "$url"
}

detect_url() {
  local waited=0
  local url=""
  while [[ "$waited" -le "$WAIT_SECONDS" ]]; do
    url="$(detect_url_once)"
    if [[ -n "$url" ]]; then
      printf '%s' "$url"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

BOT_TOKEN="${BOT_TOKEN:-$(env_value BOT_TOKEN || true)}"
ADMIN_ID="${TELEGRAM_NOTIFY_ID:-${SUPER_ADMIN_ID:-}}"
if [[ -z "$ADMIN_ID" ]]; then
  ADMIN_ID="$(env_value SUPER_ADMIN_ID || env_value SUPER_ADMIN_TG_ID || true)"
fi

if [[ -z "$BOT_TOKEN" ]]; then
  echo "BOT_TOKEN is not set and was not found in $ENV_FILE" >&2
  exit 1
fi

if [[ -z "$ADMIN_ID" ]]; then
  echo "Set TELEGRAM_NOTIFY_ID or SUPER_ADMIN_ID in $ENV_FILE" >&2
  exit 1
fi

if ! CURRENT_URL="$(detect_url)"; then
  echo "Cloudflare trycloudflare.com URL was not found in logs." >&2
  exit 1
fi

LAST_NOTIFIED="$(cat "$STATE_FILE" 2>/dev/null || true)"

if [[ "$FORCE" != "1" && "$CURRENT_URL" == "$LAST_NOTIFIED" ]]; then
  echo "Mini App URL unchanged: $CURRENT_URL"
  exit 0
fi

# Update MINI_APP_URL in .env
if grep -qE "^MINI_APP_URL=" "$ENV_FILE"; then
  sed -i "s|^MINI_APP_URL=.*|MINI_APP_URL=${CURRENT_URL}|" "$ENV_FILE"
else
  echo "MINI_APP_URL=${CURRENT_URL}" >> "$ENV_FILE"
fi
echo "Updated MINI_APP_URL in $ENV_FILE"

# Update bot menu button via Telegram API
curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Открыть приложение\",\"web_app\":{\"url\":\"${CURRENT_URL}\"}}}" \
  >/dev/null && echo "Bot menu button updated" || echo "Warning: failed to update bot menu button" >&2

# Restart bot container so it picks up new MINI_APP_URL from .env
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  docker compose -f "$COMPOSE_FILE" up -d frontend nginx 2>/dev/null \
    && echo "Frontend and nginx containers ensured" \
    || echo "Warning: failed to ensure frontend/nginx containers" >&2
  docker compose -f "$COMPOSE_FILE" restart bot 2>/dev/null \
    && echo "Bot container restarted" \
    || echo "Warning: failed to restart bot container" >&2
fi

# Notify admin
MESSAGE="Mini App URL обновлён автоматически.

${CURRENT_URL}

.env и кнопка бота обновлены."

curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${ADMIN_ID}" \
  -d "disable_web_page_preview=true" \
  --data-urlencode "text=${MESSAGE}" >/dev/null

printf '%s' "$CURRENT_URL" > "$STATE_FILE"
echo "Done. Mini App URL: $CURRENT_URL"
