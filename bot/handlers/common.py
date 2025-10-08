from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from ..context import BotContext
router = Router(name="common")


@router.message(Command("start"))
async def handle_start(message: Message, context: BotContext, member) -> None:
    intro = [
        "Привет! Это «ВПК-бот».",
        "Команды:",
        "/whoami — показать информацию о вас",
        "/link — подтвердить привязку (для личного состава)",
    ]
    if member:
        intro.insert(1, f"Ваш статус: {member.role}, отделение: {member.department}")
    else:
        intro.append(
            "Если вы есть в реестре, используйте /link и укажите своё ФИО точно как в списке."
        )
    await message.answer("\n".join(intro))


@router.message(Command("whoami"))
async def handle_whoami(message: Message, member, context: BotContext) -> None:
    if not member:
        await message.answer("Вы ещё не привязаны. Используйте /link.")
        return
    lines = [
        f"ФИО: {member.fio}",
        f"Отделение: {member.department}",
        f"Роль: {member.role}",
        f"Статус: {member.status}",
    ]
    if member.tg_username:
        lines.append(f"Username: @{member.tg_username}")
    lines.append(f"Telegram ID: {member.tg_user_id}")
    await message.answer("\n".join(lines))
