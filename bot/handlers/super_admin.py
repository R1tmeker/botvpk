from __future__ import annotations

import pytz
from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from ..config_loader import load_config, update_config
from ..context import BotContext
from ..services.exceptions import NotFoundError, ValidationServiceError
from ..utils.audit import log_action
from ..utils.roles import Role

router = Router(name="super_admin")


async def _check_super_admin(message: Message, context: BotContext) -> bool:
    if message.from_user.id != context.config.super_admin_id:
        await message.answer("Эта команда доступна только супер-админу.")
        return False
    return True


@router.message(Command("set_role"))
async def set_role(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer(
            "Как выдать роль:\n"
            "1. Узнайте ID участника (например, через «Полный состав»).\n"
            "2. Введите команду вида `/set_role 17 ADMIN` — сначала ID, затем роль.\n"
            "Допустимые роли: SUPER_ADMIN, ADMIN, LEAD, USER_CONFIRMED, USER_PENDING.",
            parse_mode=None,
        )
        return
    parts = command.args.split()
    if len(parts) != 2:
        await message.answer("Нужно указать ID и роль. Пример: `/set_role 17 ADMIN`.", parse_mode=None)
        return
    try:
        member_id = int(parts[0])
    except ValueError:
        await message.answer("ID должен быть числом. Пример: `/set_role 17 ADMIN`.", parse_mode=None)
        return
    role = parts[1].upper()
    if role not in [r.value for r in Role]:
        await message.answer("Неизвестная роль. Допустимые: SUPER_ADMIN, ADMIN, LEAD, USER_CONFIRMED, USER_PENDING.")
        return
    try:
        member = context.roster_service.set_role(member_id, role)
        await message.answer(f"Роль обновлена: {member.fio} — {member.role}")
        log_action(context, message.from_user.id, "set_role", f"id={member_id};role={role}")
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc))


@router.message(Command("set_status"))
async def set_status(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer(
            "Как изменить статус:\n"
            "1. Найдите ID участника.\n"
            "2. Выполните `/set_status 17 active` или `/set_status 17 removed`.",
            parse_mode=None,
        )
        return
    parts = command.args.split()
    if len(parts) != 2:
        await message.answer("Укажите ID и статус. Пример: `/set_status 17 removed`.", parse_mode=None)
        return
    try:
        member_id = int(parts[0])
    except ValueError:
        await message.answer("ID должен быть числом. Пример: `/set_status 17 active`.", parse_mode=None)
        return
    status = parts[1].lower()
    if status not in {"active", "removed"}:
        await message.answer("Статус может быть только active или removed.")
        return
    try:
        member = context.roster_service.set_status(member_id, status)
        await message.answer(f"Статус обновлён: {member.fio} — {member.status}")
        log_action(context, message.from_user.id, "set_status", f"id={member_id};status={status}")
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc))


@router.message(Command("reset_account"))
async def reset_account(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer(
            "Как отвязать Telegram-аккаунт участника: выполните команду `/reset_account ID`.\n"
            "После сброса пользователю нужно снова пройти /link.",
            parse_mode=None,
        )
        return
    try:
        member_id = int(command.args.strip().split()[0])
    except ValueError:
        await message.answer("ID должен быть числом. Пример: `/reset_account 17`.", parse_mode=None)
        return
    try:
        member = context.roster_service.reset_account(member_id)
        await message.answer(
            f"Привязка сброшена: {member.fio}. Telegram-аккаунт и username очищены, участнику нужно заново выполнить /link."
        )
        log_action(context, message.from_user.id, "reset_account", f"id={member_id}")
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc))


@router.message(Command("set_tz"))
async def set_timezone(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer(
            "Как сменить часовой пояс: отправьте `/set_tz Europe/Moscow` (поддерживаются идентификаторы tzdata).",
            parse_mode=None,
        )
        return
    tz_name = command.args.strip()
    if tz_name not in pytz.all_timezones:
        await message.answer("Неизвестный часовой пояс. Проверьте написание.")
        return
    update_config(context.config_path, {"TZ": tz_name})
    context.config = load_config(context.config_path)
    context.poll_scheduler.update_settings(timezone=tz_name)
    context.birthday_scheduler.update_settings(timezone=tz_name)
    await context.poll_scheduler.refresh()
    await context.birthday_scheduler.refresh()
    await message.answer(f"Часовой пояс обновлён: {tz_name}.")
    log_action(context, message.from_user.id, "set_tz", tz_name)


@router.message(Command("dryrun"))
async def set_dryrun(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer("Режим проверки без отправки: `/dryrun on` или `/dryrun off`.", parse_mode=None)
        return
    value = command.args.strip().lower()
    if value not in {"on", "off"}:
        await message.answer("Допустимые значения: on или off.")
        return
    dryrun_value = value == "on"
    update_config(context.config_path, {"DRYRUN": "true" if dryrun_value else "false"})
    context.config = load_config(context.config_path)
    context.poll_scheduler.update_settings(dryrun=dryrun_value)
    context.birthday_scheduler.update_settings(dryrun=dryrun_value)
    await message.answer(f"Dryrun = {value}")
    log_action(context, message.from_user.id, "dryrun", value)


@router.message(Command("set_leap_policy"))
async def set_leap_policy(message: Message, context: BotContext, command: CommandObject) -> None:
    if not await _check_super_admin(message, context):
        return
    if not command.args:
        await message.answer(
            "Как поздравлять тех, кто родился 29 февраля: отправьте `/set_leap_policy 28` (чтобы поздравлять 28.02) "
            "или `/set_leap_policy 01` (чтобы поздравлять 01.03).",
            parse_mode=None,
        )
        return
    value = command.args.strip()
    if value not in {"28", "01"}:
        await message.answer("Допустимые значения: 28 или 01.")
        return
    update_config(context.config_path, {"LEAP_POLICY": value})
    context.config = load_config(context.config_path)
    context.birthday_scheduler.update_settings(leap_policy=value)
    await context.birthday_scheduler.refresh()
    await message.answer(f"Политика поздравления для 29 февраля: {value}.")
    log_action(context, message.from_user.id, "set_leap_policy", value)
