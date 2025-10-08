from __future__ import annotations

from datetime import datetime, timedelta

import pytz
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..context import BotContext
from ..utils.access import ensure_role
from ..utils.pagination import chunked
from ..utils.roles import CONFIRMED_ROLES, LEAD_ROLES

router = Router(name="roster")

PAGE_SIZE = 30


def _tz_today(context: BotContext) -> datetime:
    tz = pytz.timezone(context.config.timezone)
    return datetime.now(tz)


@router.message(Command("full_roster"))
async def full_roster(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    members = context.roster_service.list_members()
    if not members:
        await message.answer("Реестр пуст.")
        return
    chunks = chunked(members, PAGE_SIZE)
    for page_number, chunk in enumerate(chunks, start=1):
        lines = [f"{m.id} | {m.fio} | {m.department}" for m in chunk]
        await message.answer("\n".join(lines) or "Нет данных.")


@router.message(Command("my_squad"))
async def my_squad(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    squad = [
        m for m in context.roster_service.list_members() if m.department == member.department
    ]
    if not squad:
        await message.answer("В вашем отделении пока никого нет.")
        return
    lines = [
        f"- {m.fio}" + (f" (@{m.tg_username})" if m.tg_username else "")
        for m in squad
    ]
    await message.answer(f"Отделение {member.department}:\n" + "\n".join(lines))


@router.message(Command("all_squads"))
async def all_squads(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    grouped = context.roster_service.group_by_department()
    if not grouped:
        await message.answer("Реестр пуст.")
        return
    parts: list[str] = []
    for department, members in grouped.items():
        members_text = "\n".join(
            f"  • {m.fio}" + (f" (@{m.tg_username})" if m.tg_username else "")
            for m in members
        )
        parts.append(f"{department}:\n{members_text}")
    pages = chunked(parts, 5)
    for page in pages:
        await message.answer("\n\n".join(page))


@router.message(Command("birthdays_today"))
async def birthdays_today(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    today = _tz_today(context).date()
    matches = context.roster_service.birthdays_on_date(today, context.config.leap_policy)
    if not matches:
        await message.answer("Сегодня именинников нет.")
        return
    lines = [
        f"{m.fio} — {m.birth_date.strftime('%d.%m.%Y')}"
        for m in matches
    ]
    await message.answer("Сегодня поздравляем:\n" + "\n".join(lines))


@router.message(Command("birthdays_week"))
async def birthdays_week(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    tz_now = _tz_today(context)
    lines: list[str] = []
    for delta in range(0, 7):
        target = tz_now.date() + timedelta(days=delta)
        matches = context.roster_service.birthdays_on_date(target, context.config.leap_policy)
        if not matches:
            continue
        header = target.strftime("%d.%m.%Y")
        rows = [
            f"  • {m.fio}" + (f" (@{m.tg_username})" if m.tg_username else "")
            for m in matches
        ]
        lines.append(f"{header}\n" + "\n".join(rows))
    if not lines:
        await message.answer("В ближайшие 7 дней именинников нет.")
        return
    await message.answer("\n\n".join(lines))


@router.message(Command("squad_report"))
async def squad_report(message: Message, context: BotContext, member) -> None:
    if not await ensure_role(message, getattr(member, "role", None), LEAD_ROLES):
        return
    squad = [
        m for m in context.roster_service.list_members() if m.department == member.department
    ]
    if not squad:
        await message.answer("Ваше отделение пустое.")
        return
    active = [m for m in squad if m.status == "active"]
    removed = [m for m in squad if m.status == "removed"]
    confirmed = [m for m in squad if m.role != "USER_PENDING"]
    lines = [
        f"Отделение: {member.department}",
        f"Всего: {len(squad)}",
        f"Активны: {len(active)}",
        f"В ожидании: {len(squad) - len(confirmed)}",
        f"Удалены: {len(removed)}",
    ]
    await message.answer("\n".join(lines))
