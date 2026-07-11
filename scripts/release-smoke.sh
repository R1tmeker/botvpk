#!/usr/bin/env bash
set -Eeuo pipefail

APP_URL="${APP_URL:-http://127.0.0.1:8081}"

health="$(curl --fail --silent --show-error "${APP_URL}/health")"
printf '%s' "${health}" | grep -q '"status":"ok"'

version="$(curl --fail --silent --show-error "${APP_URL}/version.json")"
printf '%s' "${version}" | grep -q '"build_id"'

curl --fail --silent --show-error "${APP_URL}/nginx-health" | grep -q 'ok'
printf '[smoke] API, frontend image and nginx are ready\n'
