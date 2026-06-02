#!/usr/bin/env bash
set -euo pipefail

# Prints non-secret production auth diagnostics for Telegram Mini App.
# Usage:
#   /opt/botvpk/scripts/check-miniapp-auth.sh

APP_DIR="${APP_DIR:-/opt/botvpk}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

env_value() {
  local key="$1"
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

BOT_TOKEN="$(env_value BOT_TOKEN || true)"
MINI_APP_URL="$(env_value MINI_APP_URL || true)"
ADMIN_ID="$(env_value SUPER_ADMIN_ID || env_value SUPER_ADMIN_TG_ID || true)"

if [[ -z "$BOT_TOKEN" ]]; then
  echo "BOT_TOKEN is missing in $ENV_FILE" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

echo "[auth] Checking Telegram bot token..."
GET_ME_JSON="$(curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getMe")"
GET_ME_JSON="$GET_ME_JSON" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["GET_ME_JSON"])
result = payload.get("result") or {}
print(f"[auth] Bot: @{result.get('username', 'unknown')} id={result.get('id', 'unknown')}")
PY

if [[ -n "$MINI_APP_URL" ]]; then
  echo "[auth] MINI_APP_URL: $MINI_APP_URL"
  echo "[auth] Frontend version:"
  curl -fsS "${MINI_APP_URL%/}/version.json" || true
  echo
  echo "[auth] Backend health:"
  curl -fsS "${MINI_APP_URL%/}/health" || true
  echo
else
  echo "[auth] MINI_APP_URL is missing in $ENV_FILE"
fi

echo "[auth] Default chat menu button:"
MENU_JSON="$(curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getChatMenuButton")"
MENU_JSON="$MENU_JSON" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MENU_JSON"])
button = payload.get("result") or {}
web_app = button.get("web_app") or {}
print(f"[auth] type={button.get('type', 'unknown')} text={button.get('text', '')} url={web_app.get('url', '')}")
PY

if [[ -n "$ADMIN_ID" ]]; then
  echo "[auth] Admin-specific chat menu button:"
  USER_MENU_JSON="$(curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getChatMenuButton?user_id=${ADMIN_ID}")"
  USER_MENU_JSON="$USER_MENU_JSON" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["USER_MENU_JSON"])
button = payload.get("result") or {}
web_app = button.get("web_app") or {}
print(f"[auth] type={button.get('type', 'unknown')} text={button.get('text', '')} url={web_app.get('url', '')}")
PY
fi

echo "[auth] Done. If Mini App still shows missing initData, open it from a web_app button, not from a plain URL."
