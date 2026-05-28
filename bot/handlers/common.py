from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..context import BotContext
from ..utils.audit import log_action
from ..utils.keyboards import (
    BTN_ADMIN,
    BTN_DASHBOARD,
    BTN_FULL_ROSTER,
    BTN_HELP,
    BTN_MY_SQUAD,
    BTN_REPORT,
    BTN_REPORTS,
    BTN_SCHEDULE,
    main_menu_keyboard,
)
from ..utils.roles import ADMIN_ROLES, Role, effective_role, role_label

router = Router(name="common")


class ReportStates(StatesGroup):
    waiting_text = State()


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, context: BotContext, member) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("Данные Mini App получены, но не удалось их разобрать.")
        return
    action_key = str(payload.get("key", "")).strip()
    action_title = str(payload.get("title", "раздел")).strip()
    await message.answer(f"Открываю раздел: {action_title}.", parse_mode=None)
    await _open_web_app_section(action_key, message, context, member)


async def _open_web_app_section(action_key: str, message: Message, context: BotContext, member) -> None:
    if action_key == "schedule":
        await handle_polls_button(message, context, member)
    elif action_key == "my_squad":
        from . import roster as roster_handlers

        await roster_handlers.my_squad(message, context, member)
    elif action_key == "full_roster":
        from . import roster as roster_handlers

        await roster_handlers.full_roster(message, context, member)
    elif action_key == "attendance":
        from . import attendance as attendance_handlers

        await attendance_handlers.attendance_menu(message, member, context)
    elif action_key == "mark_attendance":
        from . import attendance as attendance_handlers

        await attendance_handlers.attendance_today(message, member, context)
    elif action_key == "norms":
        from . import normatives as normatives_handlers

        await normatives_handlers.norms_menu(message, member, context)
    elif action_key == "notifications":
        from . import notifications as notification_handlers

        await notification_handlers.notifications(message, member, context)
    elif action_key == "announcements":
        from . import notifications as notification_handlers

        await notification_handlers.announcements_menu(message, member, context)
    elif action_key == "reports":
        from . import normatives as normatives_handlers

        await normatives_handlers.norm_reports(message, member, context)
    elif action_key == "admin":
        await handle_settings_button(message, context, member)
    elif action_key == "report":
        await message.answer("Напишите /report и опишите проблему одним сообщением.", parse_mode=None)
    else:
        await handle_start(message, context, member)


def _is_super_admin(member, context: BotContext) -> bool:
    if not member:
        return False
    if member.role == Role.SUPER_ADMIN.value:
        return True
    return member.tg_user_id == context.config.super_admin_id


def _is_admin(member, context: BotContext) -> bool:
    if not member:
        return False
    if effective_role(member.role) in {effective_role(role) for role in ADMIN_ROLES}:
        return True
    return _is_super_admin(member, context)


@router.message(Command("start"))
async def handle_start(message: Message, context: BotContext, member) -> None:
    intro_lines = [
        "Главное меню",
        "",
        "Выберите раздел ниже. Меню показывает только то, что доступно вашей роли.",
    ]
    if member:
        intro_lines.append(f"Роль: {role_label(member.role)}")
        intro_lines.append(f"Отделение: {member.department}")
    else:
        intro_lines.append("Вы ещё не привязаны. Для доступа к разделам выполните /link.")

    await message.answer(
        "\n".join(intro_lines),
        reply_markup=main_menu_keyboard(
            member_role=getattr(member, "role", None),
            mini_app_url=context.config.mini_app_url,
            is_admin=_is_admin(member, context),
            is_super_admin=_is_super_admin(member, context),
        ),
        parse_mode=None,
    )


@router.message(Command("whoami"))
async def handle_whoami(message: Message, member, context: BotContext) -> None:
    if not member:
        await message.answer("Вы ещё не привязаны. Используйте /link.")
        return
    details = [
        f"ФИО: {member.fio}",
        f"Роль: {role_label(member.role)}",
        f"Отделение: {member.department}",
    ]
    if member.tg_username:
        details.append(f"Username: @{member.tg_username}")
    details.append(f"Telegram ID: {member.tg_user_id}")
    await message.answer("\n".join(details))


def _help_text(member, context: BotContext) -> str:
    is_admin = _is_admin(member, context)
    is_super = _is_super_admin(member, context)

    lines: list[str] = [
        "Памятка",
        "",
        "Общие разделы:",
        "• /link — привязка к реестру по ФИО.",
        "• Расписание — ближайшие опросы и занятия.",
        "• Моё отделение / Общий состав — списки участников.",
        "• Посещаемость — свои отметки; командиры могут отмечать людей.",
        "• Нормативы — задания и сдача видео/файлов.",
        "• Уведомления — личные и отделенческие объявления.",
        "• Проблема — конфиденциальное сообщение командованию.",
    ]

    if is_admin:
        lines.extend(
            [
                "",
                "Командованию:",
                "• /notify_all текст — объявление всем отделениям.",
                "• /add_norm название | описание | дедлайн — задать норматив.",
                "• /norm_reports — последние видео/файлы по нормативам.",
                "• /mark_attendance ID статус [дата] [комментарий] — посещаемость.",
                "• /add_poll, /list_polls, /toggle_poll, /delete_poll, /edit_poll — управление опросами (data/polls.csv).",
                "• /upload_roster, /export_roster, /import_sheet — обновление реестра (перед заменой создаётся копия в backups/).",
                "• /add_member — добавить нового участника (бот подскажет шаги).",
                "• /remove_member ID / /restore_member ID — исключить или вернуть участника без перезагрузки CSV.",
                "• /set_polls_chat, /set_birthdays_chat — настроить чаты и темы для автоматических сообщений.",
                "• /delete_member ID и /edit_member ID поле=значение — редактирование состава.",
            ]
        )

    if is_super:
        lines.extend(
            [
                "",
                "Супер-админу:",
                "• /set_role ID ROLE — назначить роль участнику.",
                "• /set_status ID active|removed — изменить статус участника.",
                "• /reset_account ID — отвязать Telegram-аккаунт и username участника.",
                "• /set_tz Timezone, /dryrun on|off, /set_leap_policy 28|01 — настройки расписаний.",
                "",
                "Как выдать или забрать права:",
                "1. Найдите ID участника (команда «Полный состав» показывает его в первой колонке).",
                "2. Выполните /set_role ID ROLE. Пример: `/set_role 17 SQUAD_COMMANDER`.",
                "3. Чтобы исключить участника, выполните `/set_status 17 removed`; вернуть — `/set_status 17 active`.",
            ]
        )

    if is_admin or is_super:
        lines.extend(
            [
                "",
                "Все рабочие данные бот берёт из папки data/. Папка backups/ нужна только для восстановления после ошибок.",
            ]
        )

    return "\n".join(lines)


@router.message(Command("help"))
@router.message(F.text.casefold() == "помощь")
@router.message(F.text.casefold() == BTN_HELP.casefold())
async def handle_help(message: Message, context: BotContext, member) -> None:
    await message.answer(
        _help_text(member, context),
        reply_markup=main_menu_keyboard(
            member_role=getattr(member, "role", None),
            mini_app_url=context.config.mini_app_url,
            is_admin=_is_admin(member, context),
            is_super_admin=_is_super_admin(member, context),
        ),
        parse_mode=None,
    )


@router.message(Command("report"))
@router.message(F.text.casefold() == "донос")
@router.message(F.text.casefold() == BTN_REPORT.casefold())
async def report_start(message: Message, context: BotContext, member, state: FSMContext) -> None:
    await message.answer(
        "Опишите проблему или жалобу. Сообщение уйдёт командованию. Напишите «Отмена», чтобы прервать отправку.",
        parse_mode=None,
    )
    await state.set_state(ReportStates.waiting_text)


@router.message(ReportStates.waiting_text)
async def report_submit(message: Message, context: BotContext, member, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пришлите проблему текстом или напишите «Отмена».")
        return
    text = message.text.strip()
    if text.lower() == "отмена":
        await message.answer("Отправка жалобы отменена.")
        await state.clear()
        return

    reporter = message.from_user
    recipients = {context.config.super_admin_id}
    command_roles = {effective_role(role) for role in ADMIN_ROLES}
    for roster_member in context.roster_service.list_members():
        if effective_role(roster_member.role) in command_roles and roster_member.tg_user_id:
            recipients.add(roster_member.tg_user_id)

    payload = [
        "Новое обращение",
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
    await message.answer("Жалоба отправлена. Спасибо!")
    await state.clear()


@router.message(F.text.casefold() == "мой статус")
async def handle_status_button(message: Message, context: BotContext, member) -> None:
    await handle_whoami(message, member, context)


@router.message(F.text.casefold() == "полный состав")
@router.message(F.text.casefold() == BTN_FULL_ROSTER.casefold())
async def handle_full_roster_button(message: Message, context: BotContext, member) -> None:
    from . import roster as roster_handlers

    await roster_handlers.full_roster(message, context, member)


@router.message(F.text.casefold() == "моё отделение")
@router.message(F.text.casefold() == BTN_MY_SQUAD.casefold())
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
@router.message(F.text.casefold() == BTN_SCHEDULE.casefold())
async def handle_polls_button(message: Message, context: BotContext, member) -> None:
    polls = context.poll_service.list_polls()
    active = [poll for poll in polls if poll.is_active]
    if not active:
        await message.answer("Активных пунктов расписания пока нет.")
        return
    lines = ["Расписание:"]
    for poll in active:
        days = ", ".join(poll.days) if poll.days else "каждый день"
        lines.append(f"• {poll.title}: {days} в {poll.time_local.strftime('%H:%M')}")
    if _is_admin(member, context):
        lines.extend(["", "Управление: /add_poll, /list_polls, /edit_poll, /toggle_poll, /delete_poll"])
    await message.answer("\n".join(lines), parse_mode=None)


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
@router.message(F.text.casefold() == BTN_ADMIN.casefold())
async def handle_settings_button(message: Message, context: BotContext, member) -> None:
    if not _is_admin(member, context):
        await message.answer("Раздел доступен только командованию взвода.")
        return
    lines = [
        "Админка",
        "",
        "Состав:",
        "• /add_member — добавить участника.",
        "• /edit_member ID поле=значение — изменить ФИО, отделение, роль, статус и привязку.",
        "• /remove_member ID / /restore_member ID — убрать или вернуть участника.",
        "• /delete_member ID — удалить запись из реестра.",
        "",
        "Нормативы и объявления:",
        "• /add_norm название | описание | дедлайн — задать норматив.",
        "• /delete_norm ID — удалить норматив.",
        "• /norm_reports — посмотреть последние видео/файлы.",
        "• /notify_all текст — объявление всем отделениям.",
        "",
        "Расписание:",
        "• /add_poll, /list_polls, /edit_poll, /toggle_poll, /delete_poll.",
    ]
    if _is_super_admin(member, context):
        lines.extend(
            [
                "",
                "Настройки супер-админа:",
                "• /set_role ID ROLE — назначить роль участнику.",
                "• /set_status ID active|removed — изменить статус участника.",
                "• /reset_account ID — отвязать Telegram-аккаунт участника.",
                "• /set_tz Timezone — сменить часовой пояс расписаний.",
                "• /dryrun on|off — включить или отключить режим проверки без отправки.",
                "• /set_leap_policy 28|01 — выбрать дату поздравления для 29 февраля.",
            ]
        )
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(F.text.casefold() == BTN_DASHBOARD.casefold())
async def handle_dashboard_button(message: Message, context: BotContext, member) -> None:
    await handle_start(message, context, member)


@router.message(F.text.casefold() == BTN_REPORTS.casefold())
async def handle_reports_button(message: Message, context: BotContext, member) -> None:
    from . import normatives as normatives_handlers

    await normatives_handlers.norm_reports(message, member, context)
