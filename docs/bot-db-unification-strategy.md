# Стратегия унификации ботов и устранения CSV-долга

> Статус: план. Автор-аудит: май 2026. Связан с `tz-implementation-roadmap.md`.

## 1. Контекст и проблема

В репозитории сосуществуют **две реализации Telegram-бота**:

- **`backend/app/bot.py`** — DB-first бот (aiogram 3), работает с общей PostgreSQL.
  Разворачивается в проде: сервис `bot` в `docker-compose.yml` запускает `python -m app.bot`.
- **`bot/` + корневой `main.py`** — legacy-бот на CSV-хранилище (`data/*.csv`), в памяти.
  **Не** разворачивается через `docker-compose.yml`. Запускался вручную.

Источник путаницы («бот не видит смену роли») — именно в наличии двух кодовых баз.
Развёрнутый DB-бот рассинхрона не имеет: роль читается из таблицы `users` вживую.
Рассинхрон существует только у legacy-CSV-бота, который не в проде.

**Цель:** оставить ровно один бот (`backend/app/bot.py`) как единый источник истины,
перенести в него уникальные фичи legacy-бота, мигрировать остаточные данные из CSV,
вывести `bot/` + `main.py` + CSV из эксплуатации.

## 2. Анализ паритета фич

Фичи, которые есть только в CSV-боте и требуют решения перед удалением:

| Фича | Где в legacy | План |
|---|---|---|
| Поздравления с ДР | `bot/services/birthdays.py`, `bot/schedulers/birthdays.py`, `bot/storage/greetings.py` | **Портировать** в `backend/app/background.py` (cron-job, читает `users.birth_date`) |
| Telegram-опросы | `bot/services/polls.py`, `bot/handlers/admin_polls.py`, `bot/schedulers/poll_scheduler.py`, `data/polls.csv` | **Портировать** (новая таблица `polls` + handler в `bot.py`) ИЛИ отказаться, если не используется |
| Импорт Google Sheets | `bot/services/importer.py`, `bot/handlers/admin_roster.py` | **Отказаться** — ростер ведётся в админке мини-аппа (`/admin/users`, `/admin/join`) |
| Управление ростером в TG | `bot/handlers/admin_roster.py`, `bot/handlers/super_admin.py` | **Отказаться** — заменено админкой |
| Кастомные приветствия | `bot/storage/greetings.py`, `data/greetings.txt` | Перенести тексты в таблицу `settings` (ключ `welcome_message` уже в whitelist) |

Фичи, которые в DB-боте уже есть (удаляем CSV-дубль без портирования):
расписание, явка, нормативы (с FSM-сдачей файлов), уведомления, broadcast, заявки `/join`.

## 3. Этапы реализации

### Этап 0. Заморозка legacy (0.5 дня)
- Подтвердить через прод, что запущен только `backend/app/bot.py` (один токен на один polling — иначе конфликт `getUpdates`).
- Если legacy-бот всё ещё запускается вручную где-то — остановить (два polling на один токен = 409 Conflict).
- Зафиксировать в README, что `bot/` и `main.py` — DEPRECATED, доработке не подлежат.

### Этап 1. Аудит остаточных данных CSV (1 день)
Скрипт сравнения `data/members.csv` ↔ таблица `users` по `tg_user_id`/`telegram_id`:
- Кто есть в CSV, но отсутствует в `users` → кандидаты на миграцию.
- Расхождения ролей/отделений/статусов → лог для ручной сверки.
- Если CSV пуст или полностью покрыт БД — миграция данных не нужна, сразу к этапу 4.

Маппинг полей CSV → `users`:
| CSV | users | Преобразование |
|---|---|---|
| `fio` | `full_name` | как есть |
| `birth_date` (ДД.ММ.ГГГГ) | `birth_date` (date) | `strptime("%d.%m.%Y")` |
| `department` | `squad_id` | резолв по `squads.name`; нет — создать squad |
| `tg_username` | `username` | strip `@` |
| `tg_user_id` | `telegram_id` | int |
| `role` | `role_code` | через таблицу маппинга legacy-ролей (см. ниже) |
| `status` (`active`/`removed`) | `status_code` | `active→ACTIVE`, `removed→ARCHIVED` |

Маппинг legacy-ролей (из `bot/utils/roles.py::LEGACY_EFFECTIVE_ROLES`):
```
SUPER_ADMIN      → PLATOON_COMMANDER   (или ADMIN/SUPER_ADMIN — решить с заказчиком)
ADMIN            → DEPUTY_PLATOON_COMMANDER
LEAD             → SQUAD_COMMANDER
USER_CONFIRMED   → PARTICIPANT
USER_PENDING     → USER_PENDING
(остальные коды совпадают 1:1)
```
⚠️ Решение по `SUPER_ADMIN`/`ADMIN` принять явно: в legacy это были «командир/зам взвода»,
в новой модели ADMIN(8)/SUPER_ADMIN(9) — это техадмины. Не выдать случайно лишние права.

### Этап 2. Одноразовая миграция данных (1 день)
- Alembic data-migration ИЛИ отдельный idempotent-скрипт `backend/app/scripts/migrate_csv_members.py`.
- Идемпотентность: upsert по `telegram_id` (есть unique-индекс) и по `(full_name, birth_date)` для непривязанных.
- Прогон на копии прод-БД (есть дамп `backups/vpk-zvezda-*.dump`), сверка отчёта, затем на проде.
- Бэкап БД до прогона обязателен.

### Этап 3. Портирование уникальных фич в DB-мир (3–5 дней)
1. **Дни рождения** → новый job в `background.py`:
   `scheduler.add_job(send_birthday_greetings, "cron", hour=..., ...)`, читает `users.birth_date`,
   отправляет в `BIRTHDAYS_CHAT_ID` (из settings/env). Тексты — из `settings.welcome_message`/нового ключа.
   Учесть `leap_policy` (29 февраля), как в `bot/services/birthdays.py`.
2. **Опросы** (если нужны): таблица `polls` (вопрос, опции, расписание, chat_id), handler в `bot.py`
   на `bot.send_poll`, job в `background.py`. Если функция мертва — задокументировать отказ и не портировать.
3. **Конфиг бота** перевести с `config.txt`/`config_loader.py` на `Settings`/env (как у backend):
   `BIRTHDAYS_CHAT_ID`, `SUPER_ADMIN_ID`, `MINI_APP_URL`, `TZ` уже частично есть в `.env`.

### Этап 4. Вывод legacy из эксплуатации (1 день)
- Удалить пакет `bot/`, корневой `main.py`, `config.txt`/`config.example.txt`, `data/*.csv` (кроме `*.example.csv`, если нужны как образцы — лучше тоже убрать).
- Удалить из `requirements`/Docker всё, что нужно было только CSV-боту (если есть).
- Подчистить `logs/` от артефактов CSV-бота.
- Обновить `docs/tz-implementation-roadmap.md`: пометить DB-first бот как единственный.

### Этап 5. Единая модель ролей (0.5 дня)
- `bot/utils/roles.py` удаляется вместе с пакетом. Остаётся только `backend/app/roles.py`.
- Проверить, что в `users.role_code` после миграции нет legacy-кодов (`LEAD`, `USER_CONFIRMED`, и т.п.).
- Опционально: CHECK-constraint или Enum на `role_code`/`status_code` в БД (сейчас свободные строки).

## 4. Риски и их снятие

| Риск | Снятие |
|---|---|
| Два polling на один токен → 409 Conflict | Этап 0: убедиться, что legacy-бот не запущен |
| Потеря данных при миграции | Бэкап + прогон на копии + idempotent upsert + отчёт-сверка |
| Неверный маппинг ролей (эскалация прав) | Этап 1: явное решение по SUPER_ADMIN/ADMIN, ручная сверка лога |
| Потеря фичи ДР/опросов | Этап 3 портирует до удаления legacy |
| `birth_date` 29 февраля | Перенести `leap_policy` логику |

## 5. Критерии готовности (Definition of Done)

- [ ] В репозитории один бот — `backend/app/bot.py`. `bot/` и `main.py` удалены.
- [ ] Все участники из `members.csv` присутствуют в `users` с корректными ролями.
- [ ] Поздравления с ДР работают из БД (если фича сохраняется).
- [ ] Опросы портированы или явно сняты с поддержки (задокументировано).
- [ ] Конфиг бота — через env/`Settings`, без `config.txt`.
- [ ] В `users.role_code` нет legacy-значений.
- [ ] `tz-implementation-roadmap.md` обновлён.

## 6. Оценка трудозатрат

~7–9 человеко-дней. Критический путь: этапы 1–2 (данные) и 3 (портирование ДР/опросов).
Этапы 0, 4, 5 — быстрые, но 0 обязателен первым.
