#!/usr/bin/env bash
set -euo pipefail

# Detects the current Cloudflare Quick Tunnel URL, updates .env, refreshes the
# bot menu button via Telegram API, restarts the bot container, and notifies admin.
# Defaults are production-friendly for the immutable release layout under
# /opt/botvpk, but can be overridden:
#   APP_ROOT=/opt/botvpk TELEGRAM_NOTIFY_ID=123 bash scripts/notify-miniapp-url.sh --force

APP_ROOT="${APP_ROOT:-${APP_DIR:-/opt/botvpk}}"
SHARED_DIR="${SHARED_DIR:-$APP_ROOT/shared}"
CURRENT_DIR="${CURRENT_DIR:-$APP_ROOT/current}"
if [[ -z "${ENV_FILE:-}" ]]; then
  if [[ -f "$SHARED_DIR/.env" ]]; then
    ENV_FILE="$SHARED_DIR/.env"
  else
    ENV_FILE="$APP_ROOT/.env"
  fi
fi
STATE_FILE="${STATE_FILE:-$SHARED_DIR/.mini_app_url.notified}"
CF_SERVICE="${CF_SERVICE:-vpk-tunnel}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"
if [[ -z "${COMPOSE_FILE:-}" ]]; then
  if [[ -f "$CURRENT_DIR/docker-compose.prod.yml" ]]; then
    COMPOSE_FILE="$CURRENT_DIR/docker-compose.prod.yml"
  else
    COMPOSE_FILE="$APP_ROOT/docker-compose.prod.yml"
  fi
fi
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-botvpk}"
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

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

compose() {
  local release_version image_prefix compose_dir
  release_version="${RELEASE_VERSION:-$(cat "$SHARED_DIR/current_release" 2>/dev/null | tr -d '[:space:]' || true)}"
  image_prefix="${IMAGE_PREFIX:-$(env_value IMAGE_PREFIX || true)}"
  image_prefix="${image_prefix:-ghcr.io/r1tmeker/botvpk}"
  compose_dir="$(dirname "$COMPOSE_FILE")"
  if [[ -z "$release_version" ]]; then
    echo "Release version was not found in $SHARED_DIR/current_release" >&2
    return 1
  fi
  (
    cd "$compose_dir"
    IMAGE_PREFIX="$image_prefix" \
    RELEASE_VERSION="$release_version" \
    APP_SHARED_DIR="$SHARED_DIR" \
      docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  )
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
CURRENT_URL="${CURRENT_URL%/}"

LAST_NOTIFIED="$(cat "$STATE_FILE" 2>/dev/null || true)"

if [[ "$FORCE" != "1" && "$CURRENT_URL" == "$LAST_NOTIFIED" ]]; then
  echo "Mini App URL unchanged: $CURRENT_URL"
  exit 0
fi

mkdir -p "$(dirname "$STATE_FILE")"

# Update the Telegram Mini App URL, the website URL used by the VK bot, and CORS.
set_env_value MINI_APP_URL "$CURRENT_URL"
echo "Updated MINI_APP_URL in $ENV_FILE"

set_env_value SITE_URL "$CURRENT_URL"
echo "Updated SITE_URL in $ENV_FILE"

set_env_value API_CORS_ORIGINS "$CURRENT_URL"
echo "Updated API_CORS_ORIGINS in $ENV_FILE"

# Update bot menu button via Telegram API
curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Открыть приложение\",\"web_app\":{\"url\":\"${CURRENT_URL}\"}}}" \
  >/dev/null && echo "Bot menu button updated" || echo "Warning: failed to update bot menu button" >&2

# Restart channel bots so both Telegram and VK pick up the new URL.
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  services=(backend bot nginx)
  compose up -d frontend nginx \
    && echo "Frontend and nginx containers ensured" \
    || echo "Warning: failed to ensure frontend/nginx containers" >&2
  if compose config --services 2>/dev/null | grep -qx "vk_bot"; then
    services+=(vk_bot)
  fi
  compose up -d --force-recreate "${services[@]}" \
    && echo "Application containers recreated with fresh environment" \
    || echo "Warning: failed to recreate application containers" >&2
fi

# Notify admin with a fresh WebApp button. Old Telegram reply keyboards keep the
# URL that was embedded when the message was sent, so this button avoids stale URLs.
MESSAGE="Mini App URL обновлён автоматически.

${CURRENT_URL}

.env, сайт VK-бота и кнопка Telegram-бота обновлены.

Если старая кнопка открывает прошлый дизайн, нажми кнопку ниже или отправь /start."

curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${ADMIN_ID}" \
  -d "disable_web_page_preview=true" \
  --data-urlencode "text=${MESSAGE}" \
  --data-urlencode "reply_markup={\"inline_keyboard\":[[{\"text\":\"Открыть Mini App\",\"web_app\":{\"url\":\"${CURRENT_URL}\"}}]]}" \
  >/dev/null

printf '%s' "$CURRENT_URL" > "$STATE_FILE"
echo "Done. Mini App URL: $CURRENT_URL"
