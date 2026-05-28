from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from ..context import BotContext
from ..utils.access import ensure_role
from ..utils.audit import log_action
from ..utils.keyboards import BTN_ANNOUNCEMENTS, BTN_NOTIFICATIONS
from ..utils.roles import CONFIRMED_ROLES, PLATOON_STAFF_ROLES, SQUAD_NOTIFY_ROLES, effective_role

router = Router(name="notifications")


@router.message(Command("notifications"))
@router.message(F.text.casefold() == BTN_NOTIFICATIONS.casefold())
async def notifications(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    items = context.notifications_service.visible_for(member)
    if not items:
        await message.answer("У тебя пока нет уведомлений.")
        return
    lines = ["Твои уведомления:"]
    for item in items:
        scope = "всем" if item.scope == "all" else item.department or "лично"
        lines.append(f"\n#{item.notification_id} · {scope} · {item.created_at}\n{item.text}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("announcements"))
@router.message(F.text.casefold() == BTN_ANNOUNCEMENTS.casefold())
async def announcements_menu(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), SQUAD_NOTIFY_ROLES):
        return
    lines = [
        "Объявления",
        "",
        "• /notify_squad текст — отправить уведомление своему отделению.",
    ]
    if await _can_notify_all(message, member, silent=True):
        lines.append("• /notify_all текст — отправить уведомление всем отделениям.")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("notify_squad"))
async def notify_squad(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), SQUAD_NOTIFY_ROLES):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Формат: /notify_squad текст уведомления")
        return
    notification = context.notifications_service.create(
        sender_id=message.from_user.id,
        scope="department",
        department=member.department,
        text=text,
    )
    recipients = [
        item for item in context.roster_service.list_active_members()
        if item.department == member.department and item.tg_user_id
    ]
    sent = await _deliver(context, recipients, text)
    log_action(context, message.from_user.id, "notify_squad", f"id={notification.notification_id};sent={sent}")
    await message.answer(
        f"Уведомление сохранено для отделения {member.department}. Получателей: {len(recipients)}"
        + (" (dryrun: без отправки)." if context.config.dryrun else f", отправлено: {sent}."),
        parse_mode=None,
    )


@router.message(Command("notify_all"))
async def notify_all(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await _can_notify_all(message, member):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Формат: /notify_all текст уведомления")
        return
    notification = context.notifications_service.create(
        sender_id=message.from_user.id,
        scope="all",
        text=text,
    )
    recipients = [item for item in context.roster_service.list_active_members() if item.tg_user_id]
    sent = await _deliver(context, recipients, text)
    log_action(context, message.from_user.id, "notify_all", f"id={notification.notification_id};sent={sent}")
    await message.answer(
        f"Уведомление сохранено для всех отделений. Получателей: {len(recipients)}"
        + (" (dryrun: без отправки)." if context.config.dryrun else f", отправлено: {sent}."),
        parse_mode=None,
    )


async def _deliver(context: BotContext, recipients, text: str) -> int:
    if context.config.dryrun:
        return 0
    sent = 0
    for recipient in recipients:
        try:
            await context.bot.send_message(recipient.tg_user_id, text, parse_mode=None)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            context.logger.warning("Failed to deliver notification to %s: %s", recipient.id, exc)
    return sent


async def _can_notify_all(message: Message, member, silent: bool = False) -> bool:
    if silent:
        current = effective_role(getattr(member, "role", None))
        return current in {effective_role(role) for role in PLATOON_STAFF_ROLES}
    allowed = await ensure_role(message, getattr(member, "role", None), PLATOON_STAFF_ROLES)
    return allowed
