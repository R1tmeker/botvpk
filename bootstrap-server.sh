#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/botvpk}"
SHARED_DIR="${APP_ROOT}/shared"
ENV_FILE="${SHARED_DIR}/.env"

log() { printf '[bootstrap] %s\n' "$*"; }
fail() { printf '[bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Run bootstrap-server.sh as root"
command -v openssl >/dev/null || fail "openssl is required"

if ! command -v docker >/dev/null; then
  log "Installing Docker Engine"
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null || fail "Docker Compose plugin is required"

install -d -m 0750 "${APP_ROOT}" "${APP_ROOT}/releases" "${SHARED_DIR}" \
  "${SHARED_DIR}/backups" "${SHARED_DIR}/maintenance"
printf '<!doctype html><meta charset="utf-8"><title>ВПК Звезда</title><style>body{font:18px system-ui;display:grid;place-items:center;min-height:90vh;background:#0d1f45;color:white}</style><main><h1>ВПК «Звезда»</h1><p>Выполняется обновление. Попробуйте снова через несколько минут.</p></main>\n' \
  > "${SHARED_DIR}/maintenance/index.html"

if [[ -f "${ENV_FILE}" ]]; then
  log "Shared environment already exists; leaving it unchanged"
  exit 0
fi

BOT_TOKEN="${BOT_TOKEN:-}"
SUPER_ADMIN_ID="${SUPER_ADMIN_ID:-${SUPER_ADMIN_TG_ID:-}}"
IMAGE_PREFIX="${IMAGE_PREFIX:-}"
[[ -n "${BOT_TOKEN}" ]] || fail "Set BOT_TOKEN before bootstrap"
[[ -n "${SUPER_ADMIN_ID}" ]] || fail "Set SUPER_ADMIN_ID before bootstrap"
[[ -n "${IMAGE_PREFIX}" ]] || fail "Set IMAGE_PREFIX, for example ghcr.io/owner/repo"

DB_PASSWORD="$(openssl rand -hex 24)"
TOTP_ENCRYPTION_KEY="$(openssl rand -hex 32)"
LINK_CODE_PEPPER="$(openssl rand -hex 32)"
SESSION_SECRET="$(openssl rand -hex 32)"

umask 077
cat > "${ENV_FILE}" <<EOF
APP_ENV=production
IMAGE_PREFIX=${IMAGE_PREFIX}
BOT_TOKEN=${BOT_TOKEN}
POSTGRES_DB=vpk_zvezda
POSTGRES_USER=vpk
POSTGRES_PASSWORD=${DB_PASSWORD}
DATABASE_URL=postgresql+asyncpg://vpk:${DB_PASSWORD}@postgres:5432/vpk_zvezda
REDIS_URL=redis://redis:6379/0
SESSION_SECRET=${SESSION_SECRET}
TOTP_ENCRYPTION_KEY=${TOTP_ENCRYPTION_KEY}
LINK_CODE_PEPPER=${LINK_CODE_PEPPER}
TZ=Asia/Novosibirsk
SUPER_ADMIN_ID=${SUPER_ADMIN_ID}
UPLOADS_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=20
API_CORS_ORIGINS=
DRYRUN=false
VK_BOT_ENABLED=false
VK_GROUP_TOKEN=
VK_GROUP_ID=
VK_BOT_URL=
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CLAMAV_REQUIRED=true
SITE_URL=
MINI_APP_URL=
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.05
WEB_PUSH_VAPID_PUBLIC_KEY=
WEB_PUSH_VAPID_PRIVATE_KEY=
WEB_PUSH_VAPID_SUB=mailto:admin@example.com
EOF
chmod 0600 "${ENV_FILE}"
log "Created ${ENV_FILE}; fill optional URLs and channel credentials before deploying"
