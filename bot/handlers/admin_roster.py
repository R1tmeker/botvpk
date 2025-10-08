from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile

from ..context import BotContext
from ..config_loader import update_config, load_config
from ..services.exceptions import ValidationServiceError
from ..utils.access import ensure_role
from ..utils.roles import ADMIN_ROLES
from ..utils.audit import log_action

router = Router(name="admin_roster")


class UploadRosterState(StatesGroup):
    waiting_file = State()


@router.message(Command("upload_roster"))
async def upload_roster_start(message: Message, member, context: BotContext, state: FSMContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    await message.answer("Пришлите CSV-файл с реестром в ответ на это сообщение.")
    await state.set_state(UploadRosterState.waiting_file)


@router.message(UploadRosterState.waiting_file, F.document)
async def upload_roster_file(message: Message, state: FSMContext, context: BotContext) -> None:
    document = message.document
    if not document.file_name.endswith(".csv"):
        await message.answer("Нужен CSV-файл.")
        return
    file = await message.bot.get_file(document.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    try:
        processed = context.sheet_importer.import_from_bytes(file_bytes.read())
        log_action(context, message.from_user.id, "upload_roster", f"records={processed}")
        await message.answer(f"Импорт завершён. Всего записей: {processed}.")
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка импорта: {exc}")
    finally:
        await state.clear()


@router.message(UploadRosterState.waiting_file)
async def upload_roster_not_file(message: Message) -> None:
    await message.answer("Ожидаю документ CSV.")


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
        await message.answer(f"Импортировано записей: {total}.")
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка импорта: {exc}")


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
    context.birthday_scheduler.update_settings(
        chat_id=chat_id,
        thread_id=thread_id,
    )
    await message.answer(f"Чат для поздравлений сохранён: {chat_id}, топик: {thread_id or '-'}")
    log_action(context, message.from_user.id, "set_birthdays_chat", f"chat_id={chat_id};thread_id={thread_id}")


@router.message(Command("set_polls_chat"))
async def set_polls_chat(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    chat_id = message.chat.id
    thread_id = message.message_thread_id or ""
    update_config(
        context.config_path,
        {
            "DEFAULT_POLL_CHAT_ID": str(chat_id),
        },
    )
    context.config = load_config(context.config_path)
    await message.answer(f"Чат по умолчанию для опросов: {chat_id}. Топик: {thread_id or '-'}")
    log_action(context, message.from_user.id, "set_polls_chat", f"chat_id={chat_id};thread_id={thread_id}")
