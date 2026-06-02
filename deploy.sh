#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Deploy started: $(date)"

# load .env if present
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

if [ -f requirements.txt ]; then
    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# run migrations or other app-specific steps here (add if needed)

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user restart botvpk || systemctl restart botvpk || echo "systemd service 'botvpk' not found or restart failed"
fi

# send test telegram message if script exists
if [ -f scripts/check_telegram.py ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 scripts/check_telegram.py "Deploy finished: $(date)"
    fi
fi

echo "Deploy finished: $(date)"
#!/bin/bash
# =============================================================================
# ВПК Звезда — Автоматический деплой
# Запускать от root на чистом Ubuntu/Debian VPS
# Использование: bash deploy.sh
# =============================================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        ВПК Звезда — Деплой               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ─── Сбор секретов ──────────────────────────────────────────────────────────
# Можно передать как переменные окружения:
#   BOT_TOKEN=xxx SUPER_ADMIN_TG_ID=yyy bash deploy.sh

if [[ -z "$BOT_TOKEN" ]]; then
    warn "Нужны 2 параметра для запуска:"
    echo ""
    read -rp "  BOT_TOKEN (из @BotFather): " BOT_TOKEN
    [[ -z "$BOT_TOKEN" ]] && err "BOT_TOKEN не может быть пустым"
else
    log "BOT_TOKEN получен из переменной окружения"
fi

if [[ -z "$SUPER_ADMIN_TG_ID" ]]; then
    read -rp "  Твой Telegram ID (из @userinfobot): " SUPER_ADMIN_TG_ID
    [[ -z "$SUPER_ADMIN_TG_ID" ]] && err "Telegram ID не может быть пустым"
else
    log "SUPER_ADMIN_TG_ID получен из переменной окружения"
fi

DB_PASS=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)

echo ""
log "Секреты получены. Начинаем установку..."
echo ""

# ─── Системные зависимости ──────────────────────────────────────────────────
log "Обновление системы..."
apt-get update -qq && apt-get upgrade -y -qq

log "Установка Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash -s -- -q
    systemctl enable docker
    systemctl start docker
fi

log "Установка Docker Compose..."
if ! docker compose version &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin
fi

log "Установка nginx и утилит..."
apt-get install -y -qq nginx git curl wget unzip net-tools ufw

# ─── Cloudflare Tunnel (для HTTPS Mini App) ──────────────────────────────────
log "Установка cloudflared (Cloudflare Tunnel)..."
if ! command -v cloudflared &>/dev/null; then
    ARCH=$(dpkg --print-architecture)
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
    wget -q "$CF_URL" -O /tmp/cloudflared.deb
    dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
fi

# ─── Клонирование репозитория ────────────────────────────────────────────────
APP_DIR="/opt/botvpk"

if [[ -d "$APP_DIR" ]]; then
    warn "Папка уже существует — обновляем..."
    cd "$APP_DIR"
    git pull origin main
else
    log "Клонирование репозитория..."
    git clone https://github.com/R1tmeker/botvpk.git "$APP_DIR"
    cd "$APP_DIR"
fi

# ─── Запуск Cloudflare Tunnel (Quick Tunnel, без аккаунта) ───────────────────
log "Запуск Cloudflare Quick Tunnel..."

# Запускаем туннель в фоне, перехватываем URL
TUNNEL_LOG=/tmp/cf_tunnel.log
nohup cloudflared tunnel --url http://localhost:80 \
    --no-autoupdate \
    --logfile "$TUNNEL_LOG" \
    --loglevel warn \
    > /tmp/cf_stdout.log 2>&1 &
TUNNEL_PID=$!

# Ждём пока туннель стартует и получим URL
MINI_APP_URL=""
for i in {1..30}; do
    MINI_APP_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)
    [[ -n "$MINI_APP_URL" ]] && break
    sleep 2
done

if [[ -z "$MINI_APP_URL" ]]; then
    warn "Cloudflare Tunnel не стартовал. Используем IP для MINI_APP_URL."
    SERVER_IP=$(curl -s ifconfig.me)
    MINI_APP_URL="http://$SERVER_IP"
else
    log "Cloudflare Tunnel URL: $MINI_APP_URL"
fi

# Сохраняем PID туннеля
echo $TUNNEL_PID > /tmp/cf_tunnel.pid

# ─── Создание .env ───────────────────────────────────────────────────────────
log "Создание .env файла..."
cat > "$APP_DIR/.env" << EOF
# Telegram
BOT_TOKEN=${BOT_TOKEN}
MINI_APP_URL=${MINI_APP_URL}

# Database
DATABASE_URL=postgresql+asyncpg://vpk:${DB_PASS}@db:5432/vpk_zvezda
POSTGRES_USER=vpk
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=vpk_zvezda

# Auth
JWT_SECRET=${JWT_SECRET}
JWT_EXPIRE_MINUTES=1440

# App
SUPER_ADMIN_TG_ID=${SUPER_ADMIN_TG_ID}
TIMEZONE=Europe/Moscow
UPLOADS_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=20

# Optional
BIRTHDAY_CHAT_ID=
BIRTHDAY_THREAD_ID=
EOF

chmod 600 "$APP_DIR/.env"
log ".env создан и защищён (chmod 600)"

# ─── Конфигурация nginx ──────────────────────────────────────────────────────
log "Настройка nginx..."
cat > /etc/nginx/sites-available/vpk << 'NGINX'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 25M;

    # Mini App (React frontend)
    location / {
        root /opt/botvpk/frontend/dist;
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache, must-revalidate";
    }

    # API backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Static uploads
    location /uploads/ {
        alias /opt/botvpk/uploads/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
NGINX

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/vpk /etc/nginx/sites-enabled/vpk
nginx -t && systemctl reload nginx

# ─── Сборка фронтенда ────────────────────────────────────────────────────────
log "Сборка React Mini App..."

# Установка Node.js если нет
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi

cd "$APP_DIR/frontend"

# Создаём .env.production для vite
cat > .env.production << EOF
VITE_API_BASE_URL=/api
EOF

npm ci --quiet
npm run build

log "Фронтенд собран → $APP_DIR/frontend/dist"

# ─── Docker Compose ──────────────────────────────────────────────────────────
cd "$APP_DIR"
log "Запуск сервисов через Docker Compose..."

# Собираем и запускаем
docker compose pull --quiet 2>/dev/null || true
docker compose build --quiet
docker compose up -d --remove-orphans

# Ждём старта БД
log "Ожидание запуска PostgreSQL..."
for i in {1..30}; do
    docker compose exec -T db pg_isready -U vpk -d vpk_zvezda &>/dev/null && break
    sleep 2
done

# Применяем миграции
log "Применение миграций Alembic..."
docker compose exec -T backend alembic upgrade head

log "Применение сидов..."
docker compose exec -T backend python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.seeds import ensure_seed_data
async def main():
    async with AsyncSessionLocal() as s:
        await ensure_seed_data(s)
        await s.commit()
asyncio.run(main())
" || warn "Сиды уже применены или ошибка"

# ─── Настройка автозапуска ───────────────────────────────────────────────────
log "Настройка systemd для автозапуска Docker Compose..."
cat > /etc/systemd/system/vpk-zvezda.service << SERVICE
[Unit]
Description=VPK Zvezda Docker Compose
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/botvpk
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable vpk-zvezda

# Cloudflare Tunnel как systemd сервис
cat > /etc/systemd/system/cf-tunnel.service << SERVICE
[Unit]
Description=Cloudflare Quick Tunnel for VPK Mini App
After=network-online.target vpk-zvezda.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --url http://localhost:80 --no-autoupdate
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

# Убиваем временный туннель
kill $TUNNEL_PID 2>/dev/null || true
systemctl daemon-reload
systemctl enable cf-tunnel
systemctl start cf-tunnel

# Ждём нового URL туннеля
log "Ожидание нового URL туннеля..."
FINAL_URL=""
for i in {1..45}; do
    FINAL_URL=$(journalctl -u cf-tunnel -n 20 --no-pager 2>/dev/null | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
    [[ -n "$FINAL_URL" ]] && break
    sleep 2
done

if [[ -n "$FINAL_URL" ]]; then
    # Обновляем MINI_APP_URL в .env
    sed -i "s|MINI_APP_URL=.*|MINI_APP_URL=${FINAL_URL}|" "$APP_DIR/.env"
    # Перезапускаем backend чтобы подхватил новый URL
    docker compose restart backend bot 2>/dev/null || true
    log "Туннель запущен: $FINAL_URL"
fi

# ─── Файрвол ─────────────────────────────────────────────────────────────────
log "Настройка UFW файрвола..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ─── Проверка статуса ────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo ""
log "Проверка состояния сервисов:"
docker compose ps

echo ""
FINAL_TUNNEL=$(journalctl -u cf-tunnel -n 30 --no-pager 2>/dev/null | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "82.39.213.57")

echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}           ДЕПЛОЙ ЗАВЕРШЁН!                   ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  API:       ${GREEN}http://${SERVER_IP}/api/docs${NC}"
echo -e "  Mini App:  ${GREEN}${FINAL_TUNNEL:-http://${SERVER_IP}}${NC}"
echo ""
if [[ -n "$FINAL_TUNNEL" ]]; then
    echo -e "${YELLOW}  [WARN] Укажи этот URL в @BotFather → Bot Settings → Menu Button:${NC}"
    echo -e "  ${GREEN}${FINAL_TUNNEL}${NC}"
    echo ""
    echo -e "${YELLOW}  [WARN] URL туннеля меняется при рестарте cf-tunnel.${NC}"
    echo -e "     Для постоянного URL заведи бесплатный домен на duckdns.org${NC}"
fi
echo ""
echo -e "  Логи бэкенда: ${YELLOW}docker compose -f /opt/botvpk/docker-compose.yml logs -f backend${NC}"
echo -e "  Логи бота:    ${YELLOW}docker compose -f /opt/botvpk/docker-compose.yml logs -f bot${NC}"
echo ""
echo -e "  ${YELLOW}Не забудь поменять пароль root!  passwd${NC}"
echo ""
