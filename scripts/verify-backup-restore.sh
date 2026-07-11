#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-botvpk-preprod}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT_DIR}/.artifacts/preprod-backup"
COMPOSE=(docker compose --project-name "${PROJECT_NAME}" --env-file "${ROOT_DIR}/.env.preprod.example" -f "${ROOT_DIR}/docker-compose.yml" -f "${ROOT_DIR}/docker-compose.preprod.yml")

mkdir -p "${BACKUP_DIR}"
"${COMPOSE[@]}" exec -T postgres sh -ceu '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_dump --format=custom --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' > "${BACKUP_DIR}/database.dump"
"${COMPOSE[@]}" exec -T postgres pg_restore --list < "${BACKUP_DIR}/database.dump" > "${BACKUP_DIR}/database.contents"

"${COMPOSE[@]}" exec -T postgres sh -ceu '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  dropdb --force --if-exists -U "$POSTGRES_USER" botvpk_restore_check
  createdb -U "$POSTGRES_USER" botvpk_restore_check
'
"${COMPOSE[@]}" exec -T postgres sh -ceu '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d botvpk_restore_check
' < "${BACKUP_DIR}/database.dump"
"${COMPOSE[@]}" exec -T postgres sh -ceu '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -U "$POSTGRES_USER" -d botvpk_restore_check -Atc "SELECT COUNT(*) FROM users" >/dev/null
  dropdb --force -U "$POSTGRES_USER" botvpk_restore_check
'

docker run --rm \
  -v "botvpk_preprod_uploads:/data:ro" \
  -v "${BACKUP_DIR}:/backup" \
  alpine:3.20 sh -ceu 'tar -czf /backup/uploads.tar.gz -C /data . && tar -tzf /backup/uploads.tar.gz >/backup/uploads.contents'

echo "Backup and isolated restore verification completed: ${BACKUP_DIR}"
