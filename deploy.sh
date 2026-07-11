#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_VERSION="${1:?Usage: deploy.sh <git-sha>}"
APP_ROOT="${APP_ROOT:-/opt/botvpk}"
SHARED_DIR="${APP_SHARED_DIR:-${APP_ROOT}/shared}"
RELEASES_DIR="${APP_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_VERSION}"
CURRENT_LINK="${APP_ROOT}/current"
ENV_FILE="${SHARED_DIR}/.env"
MAINTENANCE_DIR="${SHARED_DIR}/maintenance"
MAINTENANCE_FLAG="${MAINTENANCE_DIR}/enabled"
BACKUP_DIR="${SHARED_DIR}/backups/${RELEASE_VERSION}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-botvpk}"
COMPOSE_FILE="docker-compose.prod.yml"

export RELEASE_VERSION APP_ROOT SHARED_DIR COMPOSE_PROJECT_NAME

log() { printf '[release] %s\n' "$*"; }
fail() { printf '[release] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "${RELEASE_DIR}" ]] || fail "Release directory does not exist: ${RELEASE_DIR}"
[[ -f "${ENV_FILE}" ]] || fail "Shared environment file is missing: ${ENV_FILE}"
[[ -f "${RELEASE_DIR}/${COMPOSE_FILE}" ]] || fail "Production compose file is missing"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

required_vars=(BOT_TOKEN POSTGRES_PASSWORD DATABASE_URL SESSION_SECRET TOTP_ENCRYPTION_KEY LINK_CODE_PEPPER IMAGE_PREFIX)
for name in "${required_vars[@]}"; do
  [[ -n "${!name:-}" ]] || fail "Required environment variable is empty: ${name}"
done

security_secrets=(SESSION_SECRET TOTP_ENCRYPTION_KEY LINK_CODE_PEPPER)
for name in "${security_secrets[@]}"; do
  value="${!name}"
  [[ ${#value} -ge 32 ]] || fail "${name} must be at least 32 characters"
  case "${value,,}" in
    *change_me*|*test*|*example*|*development*) fail "${name} still contains a placeholder" ;;
  esac
done

mkdir -p "${MAINTENANCE_DIR}" "${BACKUP_DIR}" "${RELEASES_DIR}"
cd "${RELEASE_DIR}"

compose() {
  docker compose --project-name "${COMPOSE_PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

previous_release=""
if [[ -L "${CURRENT_LINK}" ]]; then
  previous_release="$(basename "$(readlink -f "${CURRENT_LINK}")")"
elif [[ -f "${SHARED_DIR}/current_release" ]]; then
  previous_release="$(tr -d '[:space:]' < "${SHARED_DIR}/current_release")"
fi

restore_database() {
  local dump_file="$1"
  log "Restoring PostgreSQL backup"
  compose up -d postgres
  compose exec -T postgres sh -ceu '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    dropdb --force --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"
    createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
  '
  compose exec -T postgres sh -ceu '
    export PGPASSWORD="$POSTGRES_PASSWORD"
    pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ' < "${dump_file}"
}

rollback() {
  local exit_code=$?
  trap - ERR
  log "Deployment failed; rollback started"
  if [[ -f "${BACKUP_DIR}/database.dump" ]]; then
    compose stop backend bot vk_bot frontend || true
    restore_database "${BACKUP_DIR}/database.dump" || true
  fi
  if [[ -n "${previous_release}" && -d "${RELEASES_DIR}/${previous_release}" ]]; then
    export RELEASE_VERSION="${previous_release}"
    cd "${RELEASES_DIR}/${previous_release}"
    docker compose --project-name "${COMPOSE_PROJECT_NAME}" --env-file "${ENV_FILE}" \
      -f "${COMPOSE_FILE}" up -d --remove-orphans || true
    ln -sfn "${RELEASES_DIR}/${previous_release}" "${CURRENT_LINK}"
    printf '%s\n' "${previous_release}" > "${SHARED_DIR}/current_release"
  fi
  rm -f "${MAINTENANCE_FLAG}"
  exit "${exit_code}"
}
trap rollback ERR

log "Pulling immutable release images ${RELEASE_VERSION}"
compose pull postgres redis clamav backend bot vk_bot frontend nginx
compose up -d postgres redis clamav

log "Enabling maintenance mode and freezing writers"
touch "${MAINTENANCE_FLAG}"
compose stop backend bot vk_bot frontend || true

log "Creating PostgreSQL backup"
compose exec -T postgres sh -ceu '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_dump --format=custom --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' > "${BACKUP_DIR}/database.dump"
compose exec -T postgres pg_restore --list < "${BACKUP_DIR}/database.dump" \
  > "${BACKUP_DIR}/database.contents"

log "Creating uploads backup"
docker run --rm \
  -v "${COMPOSE_PROJECT_NAME}_uploads_data:/data:ro" \
  -v "${BACKUP_DIR}:/backup" \
  alpine:3.20 sh -ceu 'tar -czf /backup/uploads.tar.gz -C /data .'
tar -tzf "${BACKUP_DIR}/uploads.tar.gz" > "${BACKUP_DIR}/uploads.contents"

log "Applying migrations"
compose run --rm --no-deps backend alembic -c alembic.ini upgrade head
compose run --rm --no-deps backend python -m app.scripts.encrypt_totp_secrets

log "Starting application services"
compose up -d --remove-orphans postgres redis clamav backend bot vk_bot frontend nginx

log "Waiting for readiness"
for _ in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:8081/readiness >/dev/null; then
    break
  fi
  sleep 3
done
curl --fail --silent --show-error http://127.0.0.1:8081/readiness >/dev/null

if [[ -x "${RELEASE_DIR}/scripts/release-smoke.sh" ]]; then
  APP_URL="http://127.0.0.1:8081" "${RELEASE_DIR}/scripts/release-smoke.sh"
fi

log "Publishing release"
ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"
printf '%s\n' "${RELEASE_VERSION}" > "${SHARED_DIR}/current_release"
rm -f "${MAINTENANCE_FLAG}"
trap - ERR

log "Release ${RELEASE_VERSION} completed successfully"
