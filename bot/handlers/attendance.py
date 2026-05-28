from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from ..context import BotContext
from ..services.attendance import STATUS_LABELS
from ..services.exceptions import NotFoundError
from ..utils.access import ensure_role
from ..utils.audit import log_action
from ..utils.keyboards import BTN_ATTENDANCE
from ..utils.roles import ALL_ATTENDANCE_ROLES, CONFIRMED_ROLES, SQUAD_ATTENDANCE_ROLES, effective_role

router = Router(name="attendance")


@router.message(Command("attendance"))
@router.message(F.text.casefold() == BTN_ATTENDANCE.casefold())
async def attendance_menu(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return

    lines = [
        "Посещаемость",
        "",
        "• /my_attendance — мои последние отметки.",
    ]
    if _can_mark_own_department(member):
        lines.extend(
            [
                "• /attendance_today — сводка на сегодня.",
                "• /mark_attendance ID статус [дата] [комментарий] — поставить отметку.",
                "  Статусы: present, absent, late, excused.",
            ]
        )
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("my_attendance"))
async def my_attendance(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    records = context.attendance_service.list_for_member(member.id)
    if not records:
        await message.answer("По тебе пока нет отметок посещаемости.")
        return
    lines = ["Твои последние отметки:"]
    for record in records:
        comment = f" — {record.comment}" if record.comment else ""
        lines.append(f"• {record.date}: {STATUS_LABELS.get(record.status, record.status)}{comment}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("attendance_today"))
async def attendance_today(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), SQUAD_ATTENDANCE_ROLES):
        return
    department = None if _can_mark_all_departments(member) else member.department
    target_date = context.attendance_service.today()
    records = context.attendance_service.list_for_date(target_date, department=department)
    if not records:
        scope = "всем отделениям" if department is None else f"отделению {department}"
        await message.answer(f"На сегодня по {scope} ещё нет отметок.")
        return
    summary = context.attendance_service.summarize(records)
    lines = [
        f"Сводка за {target_date.strftime('%d.%m.%Y')}",
        f"Всего отметок: {summary.total}",
        f"Присутствовали: {summary.present}",
        f"Отсутствовали: {summary.absent}",
        f"Опоздали: {summary.late}",
        f"Уважительная причина: {summary.excused}",
        "",
    ]
    members_by_id = {item.id: item for item in context.roster_service.list_members()}
    for record in records[:40]:
        target = members_by_id.get(record.member_id)
        name = target.fio if target else f"ID {record.member_id}"
        lines.append(f"• {name}: {STATUS_LABELS.get(record.status, record.status)}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("mark_attendance"))
async def mark_attendance(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), SQUAD_ATTENDANCE_ROLES):
        return
    if not command.args:
        await message.answer(
            "Формат: /mark_attendance ID статус [дата YYYY-MM-DD] [комментарий]\n"
            "Пример: /mark_attendance 12 present 2026-05-28 был на построении",
            parse_mode=None,
        )
        return

    parts = command.args.split(maxsplit=3)
    if len(parts) < 2:
        await message.answer("Нужно указать ID и статус.")
        return
    try:
        member_id = int(parts[0])
        status = context.attendance_service.normalize_status(parts[1])
    except ValueError as exc:
        await message.answer(str(exc))
        return

    target_date = context.attendance_service.today()
    comment = ""
    if len(parts) >= 3:
        try:
            target_date = datetime.strptime(parts[2], "%Y-%m-%d").date()
            comment = parts[3] if len(parts) == 4 else ""
        except ValueError:
            comment = " ".join(parts[2:])

    try:
        target = context.roster_service.get_member_by_id(member_id)
    except NotFoundError as exc:
        await message.answer(str(exc))
        return

    if not _can_mark_all_departments(member) and target.department != member.department:
        await message.answer("Вы можете отмечать посещаемость только своего отделения.")
        return

    record = context.attendance_service.mark(
        target=target,
        status=status,
        marked_by=message.from_user.id,
        target_date=target_date,
        comment=comment,
    )
    log_action(context, message.from_user.id, "mark_attendance", f"id={target.id};date={record.date};status={status}")
    await message.answer(
        f"Отметка сохранена: {target.fio} — {STATUS_LABELS[status]} за {record.date}.",
        parse_mode=None,
    )


def _can_mark_own_department(member) -> bool:
    return effective_role(getattr(member, "role", None)) in {effective_role(role) for role in SQUAD_ATTENDANCE_ROLES}


def _can_mark_all_departments(member) -> bool:
    return effective_role(getattr(member, "role", None)) in {effective_role(role) for role in ALL_ATTENDANCE_ROLES}
