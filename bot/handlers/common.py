from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from ..context import BotContext
from ..utils.keyboards import main_menu_keyboard
from ..utils.roles import ADMIN_ROLES, Role

router = Router(name="common")


def _is_super_admin(member, context: BotContext) -> bool:
    if not member:
        return False
    if member.role == Role.SUPER_ADMIN.value:
        return True
    return member.tg_user_id == context.config.super_admin_id


def _is_admin(member, context: BotContext) -> bool:
    if not member:
        return False
    if member.role in {role.value for role in ADMIN_ROLES}:
        return True
    return _is_super_admin(member, context)


@router.message(Command("start"))
async def handle_start(message: Message, context: BotContext, member) -> None:
    intro_lines = [
        "Привет! Это «ВПК-бот».",
        "Доступные действия:",
        "• Мой статус — посмотреть свою роль и отделение.",
        "• Моё отделение / Полный состав — актуальные списки личного состава.",
        "• ДР сегодня / ДР ближайшие 7 дней — кого поздравляем.",
        "Если ещё не привязан, нажми «Помощь» или команду /link.",
    ]
    if member:
        intro_lines.insert(1, f"Твой статус: {member.role}, отделение: {member.department}")
    else:
        intro_lines.append("Для привязки введи своё ФИО точь-в-точь как в реестре и выполни /link.")

    await message.answer(
        "\n".join(intro_lines),
        reply_markup=main_menu_keyboard(
            is_admin=_is_admin(member, context),
            is_super_admin=_is_super_admin(member, context),
        ),
    )


@router.message(Command("whoami"))
async def handle_whoami(message: Message, member, context: BotContext) -> None:
    if not member:
        await message.answer("Вы ещё не привязаны. Используйте /link.")
        return
    details = [
        f"ФИО: {member.fio}",
        f"Отделение: {member.department}",
        f"Роль: {member.role}",
        f"Статус: {member.status}",
    ]
    if member.tg_username:
        details.append(f"Username: @{member.tg_username}")
    details.append(f"Telegram ID: {member.tg_user_id}")
    await message.answer("\n".join(details))


def _help_text(member, context: BotContext) -> str:
    is_admin = _is_admin(member, context)
    is_super = _is_super_admin(member, context)

    lines: list[str] = [
        "🆘 Помощь",
        "",
        "🔹 Общие команды:",
        "• /link — связать себя с записью в реестре по ФИО.",
        "• Мой статус — показывает ваши данные.",
        "• Моё отделение / Полный состав / Все отделения — читают data/members.csv (папка backups/ содержит только резервные копии).",
        "• ДР сегодня / ДР ближайшие 7 дней — ищут именинников по data/members.csv и шаблонам из data/greetings.txt.",
    ]

    if is_admin:
        lines.extend(
            [
                "",
                "🔹 Администраторам:",
                "• /add_poll, /list_polls, /toggle_poll, /delete_poll — управление опросами (data/polls.csv).",
                "• /upload_roster, /export_roster, /import_sheet — обновление реестра; перед заменой создаётся копия в backups/.",
                "• /set_polls_chat, /set_birthdays_chat — назначение чатов и тем для автоматических сообщений.",
            ]
        )

    if is_super:
        lines.extend(
            [
                "",
                "🔹 Супер-админу:",
                "• /set_role ID ROLE — выдать роль (SUPER_ADMIN, ADMIN, LEAD, USER_CONFIRMED, USER_PENDING).",
                "• /set_status ID active|removed — временно исключить или вернуть участника.",
                "• /set_tz Timezone, /dryrun on|off, /set_leap_policy 28|01 — настройки расписаний.",
                "",
                "⚙️ Как выдать или забрать права:",
                "1. Узнайте ID участника (команда «Полный состав» показывает его в первой колонке).",
                "2. Выполните /set_role ID ROLE, чтобы назначить новую роль. Для возврата в ожидание — укажите USER_PENDING.",
                "3. Чтобы исключить участника, выполните /set_status ID removed. Вернуть — /set_status ID active.",
            ]
        )

    if is_admin or is_super:
        lines.extend(
            [
                "",
                "ℹ️ Все рабочие данные бот берет из папки data/. Папка backups/ нужна только для отката при ошибках.",
            ]
        )

    return "\n".join(lines)


@router.message(Command("help"))
@router.message(F.text.casefold() == "помощь")
async def handle_help(message: Message, context: BotContext, member) -> None:
    await message.answer(
        _help_text(member, context),
        reply_markup=main_menu_keyboard(
            is_admin=_is_admin(member, context),
            is_super_admin=_is_super_admin(member, context),
        ),
    )


@router.message(F.text.casefold() == "мой статус")
async def handle_status_button(message: Message, context: BotContext, member) -> None:
    await handle_whoami(message, member, context)


@router.message(F.text.casefold() == "полный состав")
async def handle_full_roster_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.full_roster(message, context, member)


@router.message(F.text.casefold() == "моё отделение")
async def handle_my_squad_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.my_squad(message, context, member)


@router.message(F.text.casefold() == "все отделения")
async def handle_all_squads_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.all_squads(message, context, member)


@router.message(F.text.casefold() == "др сегодня")
async def handle_birthdays_today_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.birthdays_today(message, context, member)


@router.message(F.text.casefold() == "др ближайшие 7 дней")
async def handle_birthdays_week_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.birthdays_week(message, context, member)


@router.message(F.text.casefold() == "опросы")
async def handle_polls_button(message: Message, context: BotContext, member) -> None:
    if not _is_admin(member, context):
        await message.answer("Команда доступна только администраторам.")
        return
    await message.answer(
        "Команды для работы с опросами:\n"
        "• /add_poll — создать опрос.\n"
        "• /list_polls — показать список опросов.\n"
        "• /toggle_poll ID — включить или выключить опрос.\n"
        "• /delete_poll ID — удалить опрос.\n"
        "• /edit_poll ID — изменить параметры существующего опроса."
    )


@router.message(F.text.casefold() == "рассылка")
async def handle_broadcast_button(message: Message, context: BotContext, member) -> None:
    if not _is_admin(member, context):
        await message.answer("Команда доступна только администраторам.")
        return
    await message.answer(
        "Массовые рассылки:\n"
        "• /broadcast — запустить мастер рассылки.\n"
        "Можно выбрать отделение, роль и подтвердить отправку перед стартом."
    )


@router.message(F.text.casefold() == "реестр")
async def handle_roster_admin_button(message: Message, context: BotContext, member) -> None:
    if not _is_admin(member, context):
        await message.answer("Команда доступна только администраторам.")
        return
    await message.answer(
        "Работа с реестром:\n"
        "• /upload_roster — заменить данные CSV-файлом.\n"
        "• /export_roster — получить текущий реестр.\n"
        "• /import_sheet CSV_URL — загрузить из Google Sheets.\n"
        "Перед любой заменой автоматически создаётся резервная копия в backups/."
    )


@router.message(F.text.casefold() == "настройки")
async def handle_settings_button(message: Message, context: BotContext, member) -> None:
    if not _is_super_admin(member, context):
        await message.answer("Раздел доступен только супер-админу.")
        return
    await message.answer(
        "Настройки супер-админа:\n"
        "• /set_role ID ROLE — назначить роль участнику.\n"
        "• /set_status ID active|removed — изменить статус участника.\n"
        "• /set_tz Timezone — сменить часовой пояс расписаний.\n"
        "• /dryrun on|off — включить или отключить режим проверки без отправки сообщений.\n"
        "• /set_leap_policy 28|01 — выбрать дату поздравления для 29 февраля."
    )
