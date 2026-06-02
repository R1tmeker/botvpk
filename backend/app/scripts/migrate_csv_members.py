"""Одноразовая идемпотентная миграция участников из legacy CSV в таблицу users.

Запуск (из каталога backend, в окружении с доступом к БД):

    # 1. Сухой прогон — только отчёт, в БД ничего не пишется (по умолчанию):
    python -m app.scripts.migrate_csv_members --csv ../data/members.csv

    # 2. Применить изменения (ОБЯЗАТЕЛЬНО сделать бэкап БД до этого):
    python -m app.scripts.migrate_csv_members --csv ../data/members.csv --apply

Идемпотентность:
  - upsert по telegram_id (есть unique-индекс) для привязанных участников;
  - для непривязанных (без tg_user_id) — поиск по (full_name, birth_date),
    чтобы повторный прогон не плодил дубли.

Стратегия маппинга ролей — см. docs/bot-db-unification-strategy.md, раздел 1.
Настоящий супер-админ определяется в auth.py по telegram_id == settings.super_admin_id,
поэтому legacy SUPER_ADMIN безопасно маппится в PLATOON_COMMANDER.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models import Squad, User
from ..roles import ROLE_LEVELS

# CSV role -> backend role_code. Legacy-роли приводятся к новой модели.
ROLE_MAP = {
    "SUPER_ADMIN": "PLATOON_COMMANDER",
    "ADMIN": "DEPUTY_PLATOON_COMMANDER",
    "LEAD": "SQUAD_COMMANDER",
    "USER_CONFIRMED": "PARTICIPANT",
    "USER_PENDING": "USER_PENDING",
    # коды новой модели проходят как есть
    "PARTICIPANT": "PARTICIPANT",
    "DEPUTY_SQUAD_COMMANDER": "DEPUTY_SQUAD_COMMANDER",
    "SQUAD_COMMANDER": "SQUAD_COMMANDER",
    "DEPUTY_PLATOON_COMMANDER": "DEPUTY_PLATOON_COMMANDER",
    "PLATOON_COMMANDER": "PLATOON_COMMANDER",
}

STATUS_MAP = {"active": "ACTIVE", "removed": "ARCHIVED"}


@dataclass
class CsvRow:
    csv_id: int
    full_name: str
    birth_date: datetime | None
    department: str
    username: str | None
    telegram_id: int | None
    role_code: str
    status_code: str


def parse_csv(path: Path) -> list[CsvRow]:
    rows: list[CsvRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            role_raw = (raw["role"] or "").strip()
            status_raw = (raw["status"] or "").strip().lower()
            role_code = ROLE_MAP.get(role_raw)
            if role_code is None:
                raise SystemExit(f"Неизвестная роль '{role_raw}' (csv id={raw.get('id')})")
            if role_code not in ROLE_LEVELS:
                raise SystemExit(f"Роль '{role_code}' отсутствует в backend RoleLevel")
            status_code = STATUS_MAP.get(status_raw)
            if status_code is None:
                raise SystemExit(f"Неизвестный статус '{status_raw}' (csv id={raw.get('id')})")
            birth_raw = (raw["birth_date"] or "").strip()
            birth_date = datetime.strptime(birth_raw, "%d.%m.%Y").date() if birth_raw else None
            tg_raw = (raw["tg_user_id"] or "").strip()
            rows.append(
                CsvRow(
                    csv_id=int(raw["id"]),
                    full_name=raw["fio"].strip(),
                    birth_date=birth_date,
                    department=(raw["department"] or "").strip(),
                    username=(raw["tg_username"] or "").strip().lstrip("@") or None,
                    telegram_id=int(tg_raw) if tg_raw else None,
                    role_code=role_code,
                    status_code=status_code,
                )
            )
    return rows


async def resolve_squad_id(session, name: str, squad_cache: dict[str, int], apply: bool) -> int | None:
    if not name:
        return None
    if name in squad_cache:
        return squad_cache[name]
    squad = await session.scalar(select(Squad).where(Squad.name == name))
    if squad is None:
        if not apply:
            squad_cache[name] = -1  # маркер «будет создан»
            return -1
        squad = Squad(name=name, is_active=True)
        session.add(squad)
        await session.flush()
    squad_cache[name] = squad.id
    return squad.id


async def run(csv_path: Path, apply: bool) -> None:
    rows = parse_csv(csv_path)
    created, updated, unchanged, new_squads = 0, 0, 0, set()
    report: list[str] = []

    async with AsyncSessionLocal() as session:
        squad_cache: dict[str, int] = {}
        for row in rows:
            squad_id = await resolve_squad_id(session, row.department, squad_cache, apply)
            if squad_id == -1:
                new_squads.add(row.department)

            user = None
            if row.telegram_id is not None:
                user = await session.scalar(select(User).where(User.telegram_id == row.telegram_id))
            if user is None:
                user = await session.scalar(
                    select(User).where(User.full_name == row.full_name, User.birth_date == row.birth_date)
                )

            if user is None:
                report.append(f"  + NEW   {row.full_name} ({row.role_code}, tg={row.telegram_id or '—'})")
                created += 1
                if apply:
                    session.add(
                        User(
                            telegram_id=row.telegram_id,
                            username=row.username,
                            full_name=row.full_name,
                            birth_date=row.birth_date,
                            squad_id=None if squad_id in (None, -1) else squad_id,
                            role_code=row.role_code,
                            status_code=row.status_code,
                            linked_at=datetime.now(timezone.utc) if row.telegram_id else None,
                        )
                    )
            else:
                diffs = []
                if user.role_code != row.role_code:
                    diffs.append(f"role {user.role_code}->{row.role_code}")
                if user.status_code != row.status_code:
                    diffs.append(f"status {user.status_code}->{row.status_code}")
                if user.username != row.username:
                    diffs.append("username")
                if diffs:
                    report.append(f"  ~ UPD   {row.full_name}: {', '.join(diffs)}")
                    updated += 1
                    if apply:
                        user.role_code = row.role_code
                        user.status_code = row.status_code
                        user.username = row.username
                        if user.telegram_id is None and row.telegram_id is not None:
                            user.telegram_id = row.telegram_id
                            user.linked_at = datetime.now(timezone.utc)
                        user.updated_at = datetime.now(timezone.utc)
                else:
                    unchanged += 1

        if apply:
            await session.commit()

    print("\n".join(report) or "  (нет изменений)")
    print("\n=== ИТОГ ===")
    print(f"строк в CSV:   {len(rows)}")
    print(f"создать:       {created}")
    print(f"обновить:      {updated}")
    print(f"без изменений: {unchanged}")
    if new_squads:
        print(f"новые отделения: {', '.join(sorted(new_squads))}")
    print(f"режим:         {'APPLIED' if apply else 'DRY-RUN (--apply для записи)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Миграция участников из CSV в БД")
    parser.add_argument("--csv", required=True, type=Path, help="путь к members.csv")
    parser.add_argument("--apply", action="store_true", help="применить изменения (иначе dry-run)")
    args = parser.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"CSV не найден: {args.csv}")
    asyncio.run(run(args.csv, args.apply))


if __name__ == "__main__":
    main()
