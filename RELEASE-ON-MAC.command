#!/bin/bash
set -Eeuo pipefail
umask 077

# Run in a regular macOS Terminal. No server password is stored in this file.
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="R1tmeker/botvpk"
PATCH_FILE="${PROJECT_DIR}/.artifacts/botvpk-main-improvements.patch"
WORK_ROOT="${PROJECT_DIR}/.artifacts/mac-release"
APP_ROOT="${BOTVPK_APP_ROOT:-/opt/botvpk}"
STAGE="подготовка"
mkdir -p "${WORK_ROOT}"

fail() { printf '\nОшибка: %s\n' "$*" >&2; exit 1; }
on_error() {
  local code=$?
  printf '\nОстановлено на этапе: %s. Код: %s.\n' "$STAGE" "$code" >&2
  printf 'Рабочая копия сохранена. Успешное обновление сервера не подтверждено.\n' >&2
  exit "$code"
}
trap on_error ERR

[[ "$(uname -s)" == Darwin ]] || fail "Этот запуск предназначен для macOS."
[[ "$APP_ROOT" =~ ^/[a-zA-Z0-9_./-]+$ ]] || fail "Некорректный BOTVPK_APP_ROOT."
[[ -s "$PATCH_FILE" ]] || fail "Отсутствует .artifacts/botvpk-main-improvements.patch рядом с проектом."
/usr/bin/python3 --version >/dev/null
git --version >/dev/null
ssh -V

install_github_cli() {
  local arch tools_dir
  arch="$(uname -m)"
  case "$arch" in arm64) ;; x86_64) arch=amd64 ;; *) fail "Неизвестная архитектура: $arch" ;; esac
  tools_dir="${WORK_ROOT}/github-cli"
  mkdir -p "$tools_dir"
  printf '\nСкачиваю GitHub CLI из официального репозитория cli/cli.\n'
  curl --fail --silent --show-error --location --retry 2 --max-time 120 \
    https://api.github.com/repos/cli/cli/releases/latest > "${tools_dir}/release.json"
  /usr/bin/python3 - "${tools_dir}" "$arch" <<'PY'
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
assets = json.loads((root / "release.json").read_text())["assets"]
archive = next(a for a in assets if re.fullmatch(r"gh_[0-9.]+_macOS_" + sys.argv[2] + r"\.zip", a["name"]))
checksums = next(a for a in assets if re.fullmatch(r"gh_[0-9.]+_checksums\.txt", a["name"]))
for key, value in [("archive-name", archive["name"]), ("archive-url", archive["browser_download_url"]), ("checksum-url", checksums["browser_download_url"])]:
    if key.endswith("url") and not value.startswith("https://github.com/cli/cli/releases/download/"):
        raise SystemExit("Unexpected download host")
    (root / key).write_text(value)
PY
  curl --fail --silent --show-error --location --retry 2 --max-time 180 \
    "$(cat "${tools_dir}/archive-url")" -o "${tools_dir}/gh.zip"
  curl --fail --silent --show-error --location --retry 2 --max-time 120 \
    "$(cat "${tools_dir}/checksum-url")" -o "${tools_dir}/checksums.txt"
  /usr/bin/python3 - "${tools_dir}" <<'PY'
import hashlib, pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
name = (root / "archive-name").read_text()
expected = next(line.split()[0] for line in (root / "checksums.txt").read_text().splitlines() if line.split()[-1].lstrip("*") == name)
actual = hashlib.sha256((root / "gh.zip").read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit("GitHub CLI checksum mismatch")
with zipfile.ZipFile(root / "gh.zip") as archive:
    for entry in archive.infolist():
        path = pathlib.PurePosixPath(entry.filename)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit("Unsafe archive path")
    archive.extractall(root)
(root / "binary-path").write_text(str(root / name.removesuffix(".zip") / "bin" / "gh"))
PY
  GH="$(cat "${tools_dir}/binary-path")"
  chmod 700 "$GH"
}

STAGE="GitHub CLI и авторизация"
if command -v gh >/dev/null 2>&1; then
  GH="$(command -v gh)"
else
  install_github_cli
fi
export PATH="$(dirname "$GH"):$PATH"
"$GH" --version
if ! "$GH" auth status --hostname github.com >/dev/null 2>&1; then
  "$GH" auth login --hostname github.com --git-protocol https --scopes workflow --web
fi
"$GH" auth setup-git --hostname github.com
[[ "$("$GH" api "repos/${REPO}" --jq '.permissions.push')" == true ]] \
  || fail "У выбранного аккаунта нет права записи в ${REPO}."

STAGE="объединение с актуальным main"
RELEASE_DIR="$(mktemp -d "${WORK_ROOT}/checkout.XXXXXX")"
printf '\nРабочая копия: %s\n' "$RELEASE_DIR"
git clone --branch main --single-branch "https://github.com/${REPO}.git" "$RELEASE_DIR"
cd "$RELEASE_DIR"
git config user.name "Codex"
git config user.email "codex@openai.com"
git checkout -b release-from-mac
if git apply --reverse --check "$PATCH_FILE" 2>/dev/null; then
  printf '\nВсе изменения из патча уже присутствуют в main.\n'
else
  if ! git apply --3way --index "$PATCH_FILE"; then
    fail "Патч конфликтует с main. Отправка не выполнялась. Рабочая копия: ${RELEASE_DIR}"
  fi
  git diff --cached --check
  git commit -m "Improve responsive UI, bot workflows, appeals, learning and draft recovery"
  STAGE="отправка в main"
  git push origin HEAD:main
fi
RELEASE_SHA="$(git rev-parse HEAD)"
printf '\nВерсия в main: %s\n' "$RELEASE_SHA"

STAGE="проверки и развёртывание GitHub Actions"
RUN_ID=""
for attempt in {1..30}; do
  RUN_ID="$("$GH" run list --repo "$REPO" --workflow deploy.yml --commit "$RELEASE_SHA" \
    --event push --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  [[ -n "$RUN_ID" ]] && break
  sleep 5
done
[[ -n "$RUN_ID" ]] || fail "GitHub Actions не запустился для ${RELEASE_SHA}. Сервер не подтверждён."
printf '\nhttps://github.com/%s/actions/runs/%s\n' "$REPO" "$RUN_ID"
if ! "$GH" run watch "$RUN_ID" --repo "$REPO" --interval 10 --exit-status; then
  fail "CI или развёртывание завершились ошибкой: https://github.com/${REPO}/actions/runs/${RUN_ID}"
fi

STAGE="проверка версии и сервисов на сервере"
printf '\nПроверяю сервер 82.39.213.57. SSH при необходимости запросит пароль root.\n'
ssh -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
  -o StrictHostKeyChecking=ask -o UserKnownHostsFile="${WORK_ROOT}/known_hosts" \
  root@82.39.213.57 "bash -s -- '${RELEASE_SHA}' '${APP_ROOT}'" <<'REMOTE'
set -euo pipefail
expected="$1"
app_root="$2"
[[ "$(tr -d '[:space:]' < "${app_root}/shared/current_release")" == "$expected" ]]
[[ "$(basename "$(readlink -f "${app_root}/current")")" == "$expected" ]]
[[ ! -e "${app_root}/shared/maintenance/enabled" ]]
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8081/readiness >/dev/null
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8081/version.json \
  | python3 -c 'import json,sys; assert json.load(sys.stdin)["build_id"] == sys.argv[1], "Unexpected frontend version"' "$expected"
"${app_root}/current/scripts/release-smoke.sh"
for attempt in {1..12}; do
  all_healthy=true
  for service in postgres redis clamav backend bot vk_bot frontend nginx; do
    ids="$(docker ps -aq --filter label=com.docker.compose.project=botvpk --filter "label=com.docker.compose.service=${service}")"
    if [[ -z "$ids" || "$ids" == *$'\n'* ]]; then
      all_healthy=false
      continue
    fi
    state="$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$ids")"
    [[ "$state" == 'running healthy' ]] || all_healthy=false
    if [[ "$service" == backend || "$service" == bot || "$service" == vk_bot || "$service" == frontend ]]; then
      image="$(docker inspect --format '{{.Config.Image}}' "$ids")"
      [[ "$image" == *":${expected}" ]] || all_healthy=false
    fi
  done
  [[ "$all_healthy" == true ]] && break
  sleep 5
done
docker ps -a --filter label=com.docker.compose.project=botvpk \
  --format '{{.Names}} | {{.Status}} | {{.Image}}'
[[ "$all_healthy" == true ]]
printf '\nВерсия, API, frontend и контейнеры проверены.\n'
REMOTE
printf '\nГотово: main и сервер обновлены до %s.\n' "$RELEASE_SHA"
