#!/usr/bin/env bash
set -euo pipefail

# Sends the current Cloudflare Quick Tunnel URL to the Telegram admin when it changes.
# Defaults are production-friendly for /opt/botvpk, but can be overridden:
#   APP_DIR=/opt/botvpk TELEGRAM_NOTIFY_ID=123 bash scripts/notify-miniapp-url.sh --force

APP_DIR="${APP_DIR:-/opt/botvpk}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
STATE_FILE="${STATE_FILE:-$APP_DIR/.mini_app_url.notified}"
CF_SERVICE="${CF_SERVICE:-cf-tunnel}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"
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
ENV_URL="$(env_value MINI_APP_URL || true)"

if [[ -z "$BOT_TOKEN" ]]; then
  echo "BOT_TOKEN is not set and was not found in $ENV_FILE" >&2
  exit 1
fi

if [[ -z "$ADMIN_ID" ]]; then
  echo "Set TELEGRAM_NOTIFY_ID or SUPER_ADMIN_ID in $ENV_FILE" >&2
  exit 1
fi

if ! CURRENT_URL="$(detect_url)"; then
  echo "Cloudflare trycloudflare.com URL was not found in $CF_SERVICE logs." >&2
  exit 1
fi
LAST_NOTIFIED="$(cat "$STATE_FILE" 2>/dev/null || true)"

if [[ "$FORCE" != "1" && "$CURRENT_URL" == "$LAST_NOTIFIED" ]]; then
  echo "Mini App URL already notified: $CURRENT_URL"
  exit 0
fi

ENV_NOTE=""
if [[ -n "$ENV_URL" && "$ENV_URL" != "$CURRENT_URL" ]]; then
  ENV_NOTE=$'\n\n'"В .env сейчас другая ссылка: $ENV_URL"
fi

MESSAGE="Mini App ссылка изменилась.

Актуальная ссылка:
$CURRENT_URL

Вставь её в BotFather:
Bot Settings -> Menu Button$ENV_NOTE"

curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${ADMIN_ID}" \
  -d "disable_web_page_preview=true" \
  --data-urlencode "text=${MESSAGE}" >/dev/null

printf '%s' "$CURRENT_URL" > "$STATE_FILE"
echo "Mini App URL sent to Telegram ID $ADMIN_ID: $CURRENT_URL"
