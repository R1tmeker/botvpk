#!/usr/bin/env bash
set -euo pipefail

# Safely updates BOT_TOKEN on the production server without printing the token.
# Usage:
#   /opt/botvpk/scripts/set-bot-token.sh
#   /opt/botvpk/scripts/set-bot-token.sh '123456:ABC...'
# or:
#   BOT_TOKEN_NEW='123456:ABC...' /opt/botvpk/scripts/set-bot-token.sh

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
if [[ -z "${COMPOSE_FILE:-}" ]]; then
  if [[ -f "$CURRENT_DIR/docker-compose.prod.yml" ]]; then
    COMPOSE_FILE="$CURRENT_DIR/docker-compose.prod.yml"
  else
    COMPOSE_FILE="$APP_ROOT/docker-compose.prod.yml"
  fi
fi
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-botvpk}"
NEW_TOKEN="${1:-${BOT_TOKEN_NEW:-}}"

if [[ -z "$NEW_TOKEN" ]]; then
  if [[ -t 0 ]]; then
    read -rsp "Paste BotFather token: " NEW_TOKEN
    echo
  else
    echo "Usage: $0 '<botfather-token>'" >&2
    echo "Token is not printed by this script." >&2
    exit 2
  fi
fi
export NEW_TOKEN

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
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

compose() {
  local release_version image_prefix compose_dir
  release_version="${RELEASE_VERSION:-$(cat "$SHARED_DIR/current_release" 2>/dev/null | tr -d '[:space:]' || true)}"
  image_prefix="${IMAGE_PREFIX:-$(grep -E '^IMAGE_PREFIX=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)}"
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

echo "[token] Checking token with Telegram getMe..."
GET_ME_JSON="$(curl -fsS "https://api.telegram.org/bot${NEW_TOKEN}/getMe")"

BOT_USERNAME="$(GET_ME_JSON="$GET_ME_JSON" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["GET_ME_JSON"])
if not payload.get("ok"):
    print(payload.get("description", "Telegram getMe returned ok=false"), file=sys.stderr)
    raise SystemExit(1)
result = payload.get("result") or {}
username = result.get("username")
if not username:
    print("Telegram getMe returned no username", file=sys.stderr)
    raise SystemExit(1)
print(username)
PY
)"

echo "[token] Token belongs to @${BOT_USERNAME}"

TMP_FILE="$(mktemp)"
python3 - "$ENV_FILE" "$TMP_FILE" <<'PY'
from pathlib import Path
import os
import sys

env_path = Path(sys.argv[1])
tmp_path = Path(sys.argv[2])
new_token = os.environ["NEW_TOKEN"]

lines = env_path.read_text().splitlines()
updated = False
out = []
for line in lines:
    if line.startswith("BOT_TOKEN="):
        out.append(f"BOT_TOKEN={new_token}")
        updated = True
    else:
        out.append(line)
if not updated:
    out.append(f"BOT_TOKEN={new_token}")
tmp_path.write_text("\n".join(out) + "\n")
PY

cp "$ENV_FILE" "${ENV_FILE}.bak"
mv "$TMP_FILE" "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true

echo "[token] BOT_TOKEN updated in $ENV_FILE; backup: ${ENV_FILE}.bak"
echo "[token] Recreating backend and bot containers..."
compose up -d --force-recreate backend bot

if [[ -x "$APP_ROOT/scripts/notify-miniapp-url.sh" ]]; then
  echo "[token] Refreshing Telegram Mini App URL and button..."
  APP_ROOT="$APP_ROOT" "$APP_ROOT/scripts/notify-miniapp-url.sh" --force || echo "Warning: failed to refresh Telegram Mini App URL" >&2
fi

echo "[token] Done. Open Mini App from the fresh bot button."
