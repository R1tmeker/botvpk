from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AbsenceReason, MenuCard, Setting


ABSENCE_REASON_SEEDS = [
    ("SICK", "Болею", False, 10),
    ("STUDY", "Учёба", False, 20),
    ("WORK", "Работа", False, 30),
    ("FAMILY", "Семейные обстоятельства", False, 40),
    ("TRAVEL", "Уехал", False, 50),
    ("LATE", "Не успеваю", False, 60),
    ("TRANSPORT", "Транспорт", False, 70),
    ("OTHER", "Другое", True, 80),
]

SETTING_SEEDS = {
    "timezone": "Asia/Novosibirsk",
    "birthday_chat_id": None,
    "leap_policy": "march1",
    "default_response_deadline_minutes": "120",
    "auto_absent_after_event": "true",
}

MENU_CARD_SEEDS = [
    ("dashboard", "Главная", "сводка и быстрые действия", "dashboard", "/", None, 0, True, True),
    ("schedule", "Расписание", "занятия и ответы", "schedule", "/schedule", None, 10, True, True),
    ("attendance", "Посещаемость", "явка и оценки", "attendance", "/attendance", ["PARTICIPANT", "DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 20, True, True),
    ("normatives", "Нормативы", "задания и сдачи", "norms", "/normatives", ["PARTICIPANT", "DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 30, True, True),
    ("notifications", "Уведомления", "личные сообщения", "notifications", "/notifications", ["PARTICIPANT", "DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 40, True, True),
    ("appeals", "Обращения", "связь с командованием", "report", "/appeals", ["PARTICIPANT", "DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 50, False, True),
    ("announcements", "Объявления", "сообщения отделению", "announcements", "/announcements", ["DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 60, False, True),
    ("reports", "Отчёты", "сводки для командиров", "reports", "/reports", ["SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 70, False, True),
    ("admin", "Админка", "управление системой", "admin", "/admin", ["DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"], 80, False, True),
]


async def ensure_seed_data(session: AsyncSession) -> None:
    await seed_absence_reasons(session)
    await seed_settings(session)
    await seed_menu_cards(session)


async def seed_absence_reasons(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(AbsenceReason.code))).all())
    for code, label, requires_comment, sort_order in ABSENCE_REASON_SEEDS:
        if code not in existing:
            session.add(
                AbsenceReason(
                    code=code,
                    label=label,
                    requires_comment=requires_comment,
                    sort_order=sort_order,
                    is_active=True,
                )
            )


async def seed_settings(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(Setting.key))).all())
    for key, value in SETTING_SEEDS.items():
        if key not in existing:
            session.add(Setting(key=key, value=value))


async def seed_menu_cards(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(MenuCard.code))).all())
    for code, title, description, icon_code, route, roles, sort_order, is_required, show_badge in MENU_CARD_SEEDS:
        if code not in existing:
            session.add(
                MenuCard(
                    code=code,
                    title=title,
                    description=description,
                    icon_code=icon_code,
                    route=route,
                    roles_json=roles,
                    sort_order=sort_order,
                    is_required=is_required,
                    is_active=True,
                    show_badge=show_badge,
                )
            )
