# ВПК Звезда

Система для ВПК: Telegram-бот, Telegram Mini App, FastAPI backend и PostgreSQL. Проект закрывает роли участников и командования: расписание, состав, посещаемость, нормативы с видео/файлами, уведомления, объявления, заявки кандидатов, обращения, отчёты и админку.

## Состав
- `backend/` — FastAPI, aiogram 3, SQLAlchemy 2 async ORM, Alembic, PostgreSQL, Redis cookie-сессии, проверка Telegram WebApp `initData`, аудит действий.
- `frontend/` — React 18 + TypeScript + Vite Mini App в цветах ВПК «Звезда», с PNG-иконками и ролевыми разделами.
- `bot/` и `main.py` — legacy CSV-бот, оставлен для совместимости с текущими локальными данными.
- `backend/app/bot.py` — новый DB-first Telegram-бот для Docker Compose.
- `docker-compose.yml` — PostgreSQL, backend API, DB-first bot, frontend dev server и nginx.
- `nginx/nginx.https.example.conf` — production-пример HTTPS reverse proxy для домена и Let's Encrypt сертификатов.

## Быстрый запуск новой версии
```powershell
Copy-Item .env.example .env
# Заполните .env реальными значениями BOT_TOKEN, SESSION_SECRET, TOTP_ENCRYPTION_KEY,
# LINK_CODE_PEPPER, POSTGRES_PASSWORD, DATABASE_URL, SUPER_ADMIN_ID и MINI_APP_URL.
docker compose up --build
```

Адреса по умолчанию:
- API: `http://localhost:8000`
- Mini App dev: `http://localhost:5173`
- nginx: `http://localhost:8080`

## Проверки
```powershell
.\.venv\Scripts\python.exe -m compileall -q backend main.py bot
cd frontend
npm run build
```

## Продакшен и бэкапы
HTTPS-настройка, ежедневные `pg_dump`-бэкапы и восстановление описаны в [docs/production-ops.md](docs/production-ops.md).

## Роли
- `PARTICIPANT` — расписание, своё отделение, общий состав, сдача нормативов, своя посещаемость, уведомления.
- `DEPUTY_SQUAD_COMMANDER` — права участника, объявления/уведомления и посещаемость своего отделения.
- `SQUAD_COMMANDER` — права заместителя, плюс посещаемость всех отделений.
- `DEPUTY_PLATOON_COMMANDER` и `PLATOON_COMMANDER` — управление нормативами, общие объявления, видеоотчёты, состав, роли, отчёты.
- `ADMIN` и `SUPER_ADMIN` — системная админка, меню, настройки, аудит.

## Приватность
Реальные `.env`, `config.txt`, `sheet_url.txt`, `data/*.csv`, `data/*.txt`, загрузки, логи и бэкапы не должны попадать в git. В репозитории остаются только примеры: `.env.example`, `config.example.txt`, `data/*.example.*`.

Если токен бота случайно был отправлен в чат или попал в чужие руки, его нужно перевыпустить через BotFather и заменить в локальном `.env`/`config.txt`.
