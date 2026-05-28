from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..config_loader import load_config, update_config
from ..context import BotContext
from ..services.exceptions import NotFoundError, ValidationServiceError
from ..utils.access import ensure_role
from ..utils.audit import log_action
from ..utils.roles import ADMIN_ROLES

router = Router(name="admin_roster")


class UploadRosterState(StatesGroup):
    waiting_file = State()


class AddMemberStates(StatesGroup):
    fio = State()
    birth_date = State()
    department = State()
    username = State()
    confirm = State()


def _skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
    )


@router.message(Command("upload_roster"))
async def upload_roster_start(message: Message, member, context: BotContext, state: FSMContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    await message.answer("Пришлите CSV-файл с новым реестром в ответ на это сообщение.")
    await state.set_state(UploadRosterState.waiting_file)


@router.message(UploadRosterState.waiting_file, F.document)
async def upload_roster_file(message: Message, state: FSMContext, context: BotContext) -> None:
    document = message.document
    if not document.file_name.lower().endswith(".csv"):
        await message.answer("Нужен файл в формате CSV.")
        return
    file = await context.bot.get_file(document.file_id)
    file_bytes = await context.bot.download_file(file.file_path)
    try:
        processed = context.sheet_importer.import_from_bytes(file_bytes.read())
        log_action(context, message.from_user.id, "upload_roster", f"records={processed}")
        await message.answer(
            f"Импорт завершён. Прочитано строк: {processed}. "
            "Роли, статусы и привязки существующих участников сохранены."
        )
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка импорта: {exc}")
    finally:
        await state.clear()


@router.message(UploadRosterState.waiting_file)
async def upload_roster_not_file(message: Message) -> None:
    await message.answer("Ожидаю CSV-файл.")


@router.message(Command("export_roster"))
async def export_roster(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    csv_text = context.roster_service.export_to_csv()
    file_path = context.roster_service.storage.path
    temp_path = file_path.parent / "export_members.csv"
    temp_path.write_text(csv_text, encoding="utf-8")
    await message.answer_document(FSInputFile(path=temp_path, filename="members.csv"))
    temp_path.unlink(missing_ok=True)
    log_action(context, message.from_user.id, "export_roster", None)


@router.message(Command("import_sheet"))
async def import_sheet(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    url = command.args.strip() if command.args else None
    try:
        total = context.sheet_importer.import_from_url(url)
        log_action(context, message.from_user.id, "import_sheet", f"url={url or 'stored'};records={total}")
        await message.answer(
            f"Импортировано записей: {total}. Роли, статусы и Telegram-привязки сохранены."
        )
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка импорта: {exc}")


@router.message(Command("add_member"))
async def add_member_start(message: Message, member, context: BotContext, state: FSMContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    await message.answer("Введите ФИО нового участника.")
    await state.set_state(AddMemberStates.fio)


@router.message(AddMemberStates.fio)
async def add_member_fio(message: Message, state: FSMContext) -> None:
    fio = message.text.strip()
    if len(fio.split()) < 2:
        await message.answer("Укажите ФИО полностью, например: Иванов Иван Иванович.")
        return
    await state.update_data(fio=fio)
    await state.set_state(AddMemberStates.birth_date)
    await message.answer("Введите дату рождения (ДД.ММ.ГГГГ).")


@router.message(AddMemberStates.birth_date)
async def add_member_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth = datetime.strptime(message.text.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат. Пример: 24.05.2008")
        return
    await state.update_data(birth_date=birth)
    await state.set_state(AddMemberStates.department)
    await message.answer("Укажите отделение (текстом).")


@router.message(AddMemberStates.department)
async def add_member_department(message: Message, state: FSMContext) -> None:
    department = message.text.strip()
    if not department:
        await message.answer("Отделение не может быть пустым.")
        return
    await state.update_data(department=department)
    await state.set_state(AddMemberStates.username)
    await message.answer(
        "Введите username (без @), если он есть. Если хотите пропустить — нажмите «Пропустить».",
        reply_markup=_skip_keyboard(),
    )


@router.message(AddMemberStates.username)
async def add_member_username(message: Message, state: FSMContext) -> None:
    username = message.text.strip()
    if username.lower() == "пропустить":
        username = ""
    if username.startswith("@"):
        username = username[1:]
    await state.update_data(username=username or None)
    data = await state.get_data()
    summary = [
        "Проверь данные:",
        f"ФИО: {data['fio']}",
        f"Дата рождения: {data['birth_date']}",
        f"Отделение: {data['department']}",
        f"Username: @{data['username']}" if data["username"] else "Username: не указан",
        "",
        "Добавить участника? (да/нет)",
    ]
    await state.set_state(AddMemberStates.confirm)
    await message.answer("\n".join(summary), reply_markup=ReplyKeyboardRemove())


@router.message(AddMemberStates.confirm)
async def add_member_confirm(message: Message, state: FSMContext, context: BotContext) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответьте «да» или «нет».")
        return
    if answer == "нет":
        await message.answer("Добавление отменено.")
        await state.clear()
        return

    data = await state.get_data()
    try:
        member = context.roster_service.add_member(
            fio=data["fio"],
            birth_date=data["birth_date"],
            department=data["department"],
            tg_username=data["username"],
        )
        log_action(context, message.from_user.id, "add_member", f"id={member.id}")
        await message.answer(f"Участник добавлен. Новый ID: {member.id}")
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка: {exc}")
    finally:
        await state.clear()


@router.message(Command("remove_member"))
async def remove_member(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /remove_member ID (переводит участника в статус removed).")
        return
    try:
        member_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        updated = context.roster_service.set_status(member_id, "removed")
        log_action(context, message.from_user.id, "remove_member", f"id={member_id}")
        await message.answer(f"Участник {updated.fio} помечен как removed.")
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc))


@router.message(Command("restore_member"))
async def restore_member(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /restore_member ID (возвращает статус active).")
        return
    try:
        member_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        updated = context.roster_service.set_status(member_id, "active")
        log_action(context, message.from_user.id, "restore_member", f"id={member_id}")
        await message.answer(f"Участник {updated.fio} снова активен.")
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc))


@router.message(Command("delete_member"))
async def delete_member(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /delete_member ID (удаляет запись из реестра).")
        return
    try:
        member_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        removed = context.roster_service.delete_member(member_id)
        log_action(context, message.from_user.id, "delete_member", f"id={member_id}")
        await message.answer(f"Участник {removed.fio} удалён из реестра.")
    except NotFoundError as exc:
        await message.answer(str(exc))


@router.message(Command("edit_member"))
async def edit_member(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args or "=" not in command.args:
        await message.answer(
            "Формат: /edit_member ID поле=значение\n"
            "Поля: fio, birth_date, department, tg_username, tg_user_id, role, status.",
            parse_mode=None,
        )
        return
    try:
        member_id_raw, update_text = command.args.split(maxsplit=1)
        member_id = int(member_id_raw)
        field, value = [part.strip() for part in update_text.split("=", 1)]
    except ValueError:
        await message.answer("Пример: /edit_member 12 department=2 Отделение", parse_mode=None)
        return
    try:
        updated = context.roster_service.edit_member_field(member_id, field, value)
        log_action(context, message.from_user.id, "edit_member", f"id={member_id};field={field}")
        await message.answer(f"Участник обновлён: {updated.id} · {updated.fio}", parse_mode=None)
    except (ValidationServiceError, NotFoundError) as exc:
        await message.answer(str(exc), parse_mode=None)


@router.message(Command("set_birthdays_chat"))
async def set_birthdays_chat(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    update_config(
        context.config_path,
        {
            "BIRTHDAYS_CHAT_ID": str(chat_id),
            "BIRTHDAYS_THREAD_ID": str(thread_id or ""),
        },
    )
    context.config = load_config(context.config_path)
    context.birthday_scheduler.update_settings(chat_id=chat_id, thread_id=thread_id)
    await message.answer(f"Чат для поздравлений сохранён: {chat_id}, топик: {thread_id or '-'}")
    log_action(context, message.from_user.id, "set_birthdays_chat", f"chat_id={chat_id};thread_id={thread_id}")


@router.message(Command("set_polls_chat"))
async def set_polls_chat(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    chat_id = message.chat.id
    thread_id = message.message_thread_id or ""
    update_config(context.config_path, {"DEFAULT_POLL_CHAT_ID": str(chat_id)})
    context.config = load_config(context.config_path)
    await message.answer(f"Чат по умолчанию для опросов: {chat_id}. Топик: {thread_id or '-'}")
    log_action(context, message.from_user.id, "set_polls_chat", f"chat_id={chat_id};thread_id={thread_id}")

