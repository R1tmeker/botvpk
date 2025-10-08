# ВПК-бот

Telegram-бот для автоматизации работы личного состава ВПК: опросы, поздравления и рассылки без использования СУБД. Все данные хранятся в CSV/txt файлах.

## Возможности
- привязка участников по ФИО через /link
- просмотр состава, отделений и ближайших ДР (/full_roster, /my_squad, /all_squads, /birthdays_today, /birthdays_week)
- автоматические опросы по расписанию из data/polls.csv
- автоматические поздравления в чат по шаблонам из data/greetings.txt
- массовые рассылки с лимитом скорости и тестовым режимом (/broadcast)
- импорт/экспорт реестра (/upload_roster, /export_roster, /import_sheet)
- управление ролями и конфигурацией для супер-админа (/set_role, /set_status, /set_tz, /dryrun, /set_leap_policy)
- все ключевые действия администраторов логируются в logs/<дата>.log

## Требования
- Python 3.11+
- зависимые пакеты из 
equirements.txt

## Быстрый старт
`powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
`

Перед запуском укажите реальные значения в config.txt:
`
BOT_TOKEN=<токен бота>
TZ=Europe/Moscow
BIRTHDAYS_CHAT_ID=<id целевого чата или группы>
BIRTHDAYS_THREAD_ID=<id топика при необходимости>
BIRTHDAYS_TIME=09:00
DEFAULT_POLL_CHAT_ID=<чат по умолчанию для опросов>
LEAP_POLICY=28
DRYRUN=false
SUPER_ADMIN_ID=795307805
`

## Структура проекта
`
.
├── main.py                  # точка входа, инициализация бота и планировщика
├── config.txt               # конфигурация окружения
├── requirements.txt
├── data/
│   ├── members.csv          # реестр личного состава
│   ├── polls.csv            # расписания опросов
│   └── greetings.txt        # шаблоны поздравлений
├── bot/
│   ├── context.py
│   ├── config_loader.py
│   ├── handlers/            # обработчики команд по ролям
│   ├── middlewares/
│   ├── schedulers/
│   ├── services/            # бизнес-логика и работа с CSV
│   ├── storage/
│   └── utils/
├── backups/                 # резервные копии CSV (создаются автоматически)
└── logs/                    # ежедневные логи (создаются автоматически)
`

## Основные роли
- **SUPER_ADMIN** – полные права, ID берётся из config.txt
- **ADMIN** – управление опросами, рассылками, реестром
- **LEAD** – расширенный просмотр своего отделения
- **USER_CONFIRMED** – подтверждённый участник
- **USER_PENDING** – ожидает привязки

## Работа с расписаниями
- планировщик APScheduler пересобирается при каждом запуске и после изменения опросов
- schedule_type может быть weekly, daily или once
- режим dryrun (/dryrun on) ведёт только логирование без отправки сообщений

## Импорт из Google Sheets
- опубликуйте таблицу как CSV («Файл → Опубликовать в интернете»)
- выполните /import_sheet <csv_url> либо сохраните URL в sheet_url.txt
- перед заменой выполняется валидация и резервное копирование старого members.csv

## Логи
- все административные действия пишутся в logs/YYYY-MM-DD.log
- директории ackups и logs создаются автоматически, их можно очищать вручную

## Проверка перед продом
- убедитесь, что в data/greetings.txt минимум 5 шаблонов с плейсхолдером {name}
- перед продуктивным запуском рекомендуем включить DRYRUN=true и убедиться, что расписания работают корректно

