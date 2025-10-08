from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..context import BotContext
from ..utils.audit import log_action
from ..utils.keyboards import main_menu_keyboard
from ..utils.roles import ADMIN_ROLES, Role

router = Router(name="common")


class ReportStates(StatesGroup):
    waiting_text = State()


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
        "• Моё отделение / Полный состав — списки из актуального реестра.",
        "• ДР сегодня / ДР ближайшие 7 дней — напоминания о днях рождения.",
        "Если ещё не привязан, нажми «Помощь» или команду /link.",
    ]
    if member:
        intro_lines.insert(1, f"Твой статус: {member.role}, отделение: {member.department}")
    else:
        intro_lines.append("Для привязки введи своё ФИО точь‑в‑точь из списка и выполни /link.")

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
        "• /link — привязка к реестру по ФИО.",
        "• Мой статус — показывает ваши данные.",
        "• Моё отделение / Полный состав / Все отделения — читают файл data/members.csv (backups/ хранит только резервные копии).",
        "• ДР сегодня / ДР ближайшие 7 дней — дни рождения по data/members.csv и data/greetings.txt.",
        "• ДОНОС — отправить жалобу супер-админам.",
    ]

    if is_admin:
        lines.extend(
            [
                "",
                "🔹 Администраторам:",
                "• /add_poll, /list_polls, /toggle_poll, /delete_poll, /edit_poll — управление опросами (data/polls.csv).",
                "• /upload_roster, /export_roster, /import_sheet — обновление реестра (перед заменой создаётся копия в backups/).",
                "• /add_member — добавить нового участника (бот подскажет шаги).",
                "• /remove_member ID / /restore_member ID — исключить или вернуть участника без перезагрузки CSV.",
                "• /set_polls_chat, /set_birthdays_chat — настроить чаты и темы для автоматических сообщений.",
                "• /delete_member ID — полностью удалить участника из реестра.",
            ]
        )

    if is_super:
        lines.extend(
            [
                "",
                "🔹 Супер-админу:",
                "• /set_role ID ROLE — назначить роль (SUPER_ADMIN, ADMIN, LEAD, USER_CONFIRMED, USER_PENDING).",
                "• /set_status ID active|removed — изменить статус участника.",
                "• /reset_account ID — отвязать Telegram-аккаунт и username участника.",
                "• /set_tz Timezone, /dryrun on|off, /set_leap_policy 28|01 — настройки расписаний.",
                "",
                "⚙️ Как выдать или забрать права:",
                "1. Найдите ID участника (команда «Полный состав» показывает его в первой колонке).",
                "2. Выполните /set_role ID ROLE. Пример: `/set_role 17 ADMIN`.",
                "3. Чтобы исключить участника, выполните `/set_status 17 removed`; вернуть — `/set_status 17 active`.",
            ]
        )

    if is_admin or is_super:
        lines.extend(
            [
                "",
                "ℹ️ Все рабочие данные бот берёт из папки data/. Папка backups/ нужна только для восстановления после ошибок.",
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


@router.message(Command("report"))
@router.message(F.text.casefold() == "донос")
async def report_start(message: Message, context: BotContext, member, state: FSMContext) -> None:
    await message.answer(
        "Опиши проблему или жалобу. Напиши «Отмена», чтобы прервать отправку.")
    await state.set_state(ReportStates.waiting_text)


@router.message(ReportStates.waiting_text)
async def report_submit(message: Message, context: BotContext, member, state: FSMContext) -> None:
    text = message.text.strip()
    if text.lower() == "отмена":
        await message.answer("Отправка жалобы отменена.")
        await state.clear()
        return

    reporter = message.from_user
    recipients = {context.config.super_admin_id}
    for roster_member in context.roster_service.list_members():
        if roster_member.role == Role.SUPER_ADMIN.value and roster_member.tg_user_id:
            recipients.add(roster_member.tg_user_id)

    payload = [
        "📣 Новый донос",
        f"От: {reporter.full_name} (ID {reporter.id})",
    ]
    if reporter.username:
        payload[-1] += f" @{reporter.username}"
    if member:
        payload.extend(
            [
                f"ФИО по реестру: {member.fio}",
                f"Отделение: {member.department}",
                f"Роль: {member.role}",
            ]
        )
    payload.append("")
    payload.append(text)
    message_text = "\n".join(payload)

    for admin_id in recipients:
        try:
            await context.bot.send_message(admin_id, message_text)
        except Exception:  # noqa: BLE001
            continue

    log_action(context, reporter.id, "report", None)
    await message.answer("Жалоба отправлена супер-админам. Спасибо!")
    await state.clear()


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
        "• /edit_poll ID — изменить существующий опрос."
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
        "• /add_member — добавить участника через бот.\n"
        "• /remove_member ID / /restore_member ID — удалить или вернуть участника.\n"
        "• /delete_member ID — полностью удалить участника из реестра.\n"
        "Перед любой заменой создаётся резервная копия в папке backups/."
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
        "• /reset_account ID — отвязать Telegram-аккаунт участника.\n"
        "• /set_tz Timezone — сменить часовой пояс расписаний.\n"
        "• /dryrun on|off — включить или отключить режим проверки без отправки.\n"
        "• /set_leap_policy 28|01 — выбрать дату поздравления для 29 февраля."
    )
