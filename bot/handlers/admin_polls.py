from __future__ import annotations

from datetime import time
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from ..context import BotContext
from ..services.exceptions import NotFoundError, ValidationServiceError
from ..services.polls import PollInput
from ..utils.access import ensure_role
from ..utils.audit import log_action
from ..utils.roles import ADMIN_ROLES

router = Router(name="admin_polls")


class AddPollStates(StatesGroup):
    title = State()
    question = State()
    options = State()
    is_anonymous = State()
    allows_multiple = State()
    schedule_type = State()
    days = State()
    time_local = State()
    target_chat = State()
    thread_id = State()
    confirm = State()


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"да", "true", "1", "yes", "y"}:
        return True
    if normalized in {"нет", "false", "0", "no", "n"}:
        return False
    raise ValueError("Ожидаю ответ «да» или «нет».")


def _skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить")]],
        resize_keyboard=True,
    )


@router.message(Command("add_poll"))
async def add_poll_start(message: Message, member, context: BotContext, state: FSMContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    await state.set_state(AddPollStates.title)
    await message.answer("Создаём опрос. Шаг 1/10.\nВведите короткое название опроса.")


@router.message(AddPollStates.title)
async def add_poll_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AddPollStates.question)
    await message.answer("Шаг 2/10. Укажите текст вопроса.")


@router.message(AddPollStates.question)
async def add_poll_question(message: Message, state: FSMContext) -> None:
    await state.update_data(question=message.text.strip())
    await state.set_state(AddPollStates.options)
    await message.answer("Шаг 3/10. Перечислите варианты через символ | (минимум два).")


@router.message(AddPollStates.options)
async def add_poll_options(message: Message, state: FSMContext) -> None:
    options = [option.strip() for option in message.text.split("|") if option.strip()]
    if len(options) < 2:
        await message.answer("Нужно минимум два варианта, разделённых символом |.")
        return
    await state.update_data(options=options)
    await state.set_state(AddPollStates.is_anonymous)
    await message.answer("Шаг 4/10. Опрос анонимный? (да/нет)")


@router.message(AddPollStates.is_anonymous)
async def add_poll_is_anonymous(message: Message, state: FSMContext) -> None:
    try:
        value = _parse_bool(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(is_anonymous=value)
    await state.set_state(AddPollStates.allows_multiple)
    await message.answer("Шаг 5/10. Разрешить отвечать несколькими вариантами? (да/нет)")


@router.message(AddPollStates.allows_multiple)
async def add_poll_allows_multiple(message: Message, state: FSMContext) -> None:
    try:
        value = _parse_bool(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(allows_multiple=value)
    await state.set_state(AddPollStates.schedule_type)
    await message.answer("Шаг 6/10. Тип расписания (weekly/daily/once).")


@router.message(AddPollStates.schedule_type)
async def add_poll_schedule_type(message: Message, state: FSMContext) -> None:
    schedule_type = message.text.strip().lower()
    if schedule_type not in {"weekly", "daily", "once"}:
        await message.answer("Допустимые варианты: weekly, daily, once.")
        return
    await state.update_data(schedule_type=schedule_type)
    if schedule_type == "weekly":
        await state.set_state(AddPollStates.days)
        await message.answer("Шаг 7/10. Укажите дни через | (например: MON|WED|FRI).")
    else:
        await state.update_data(days=[])
        await state.set_state(AddPollStates.time_local)
        await message.answer("Шаг 7/10. Укажите время в формате HH:MM.")


@router.message(AddPollStates.days)
async def add_poll_days(message: Message, state: FSMContext) -> None:
    days = [day.strip().upper() for day in message.text.split("|") if day.strip()]
    if not days:
        await message.answer("Нужно указать хотя бы один день.")
        return
    await state.update_data(days=days)
    await state.set_state(AddPollStates.time_local)
    await message.answer("Шаг 8/10. Укажите время в формате HH:MM.")


@router.message(AddPollStates.time_local)
async def add_poll_time(message: Message, state: FSMContext, context: BotContext) -> None:
    try:
        hour, minute = map(int, message.text.strip().split(":"))
        poll_time = time(hour=hour, minute=minute)
    except Exception:
        await message.answer("Неверный формат. Пример: 19:30.")
        return
    await state.update_data(time_local=poll_time)
    await state.set_state(AddPollStates.target_chat)
    if context.config.default_poll_chat_id is not None:
        await message.answer(
            "Шаг 9/10. ID чата для отправки.\n"
            "Чтобы использовать чат по умолчанию, нажмите «Пропустить».",
            reply_markup=_skip_keyboard(),
        )
    else:
        await message.answer(
            "Шаг 9/10. Укажите ID чата для отправки (бот должен иметь права на отправку опросов).",
            reply_markup=ReplyKeyboardRemove(),
        )


@router.message(AddPollStates.target_chat)
async def add_poll_target_chat(message: Message, state: FSMContext, context: BotContext) -> None:
    raw = message.text.strip()
    if raw.lower() == "пропустить":
        raw = ""
    chat_id: Optional[int]
    if raw:
        try:
            chat_id = int(raw)
        except ValueError:
            await message.answer("ID чата должен быть числом или нажмите «Пропустить».")
            return
    else:
        chat_id = context.config.default_poll_chat_id
        if chat_id is None:
            await message.answer("Чат по умолчанию не задан. Введите числовой ID.")
            return
    await state.update_data(target_chat_id=chat_id)
    await state.set_state(AddPollStates.thread_id)
    await message.answer(
        "Шаг 10/10. ID топика (если нужен).\n"
        "Если не используете темы — нажмите «Пропустить».",
        reply_markup=_skip_keyboard(),
    )


@router.message(AddPollStates.thread_id)
async def add_poll_thread_id(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw.lower() == "пропустить":
        raw = ""
    thread_id = None
    if raw:
        try:
            thread_id = int(raw)
        except ValueError:
            await message.answer("ID топика должен быть числом или нажмите «Пропустить».")
            return
    await state.update_data(message_thread_id=thread_id)
    data = await state.get_data()
    preview = [
        "Проверь параметры опроса:",
        f"Название: {data['title']}",
        f"Вопрос: {data['question']}",
        f"Варианты: {' | '.join(data['options'])}",
        f"Анонимный: {'да' if data['is_anonymous'] else 'нет'}",
        f"Несколько ответов: {'да' if data['allows_multiple'] else 'нет'}",
        f"Тип расписания: {data['schedule_type']}",
        f"Дни: {', '.join(data['days']) if data['days'] else '-'}",
        f"Время: {data['time_local'].strftime('%H:%M')}",
        f"Чат: {data['target_chat_id']}",
        f"Топик: {data['message_thread_id'] or '-'}",
        "",
        "Отправить? (да/нет)",
    ]
    await message.answer("\n".join(preview), reply_markup=ReplyKeyboardRemove())
    await state.set_state(AddPollStates.confirm)


@router.message(AddPollStates.confirm)
async def add_poll_confirm(message: Message, state: FSMContext, context: BotContext) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответь «да» или «нет».")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Создание опроса отменено.")
        return
    data = await state.get_data()
    poll_input = PollInput(
        poll_id=None,
        title=data["title"],
        question=data["question"],
        options=data["options"],
        is_anonymous=data["is_anonymous"],
        allows_multiple_answers=data["allows_multiple"],
        schedule_type=data["schedule_type"],
        days=data["days"],
        time_local=data["time_local"],
        target_chat_id=data["target_chat_id"],
        message_thread_id=data["message_thread_id"],
        is_active=True,
    )
    try:
        poll = context.poll_service.save_poll(poll_input)
        await context.poll_scheduler.refresh()
        log_action(context, message.from_user.id, "add_poll", f"poll_id={poll.poll_id}")
        await message.answer(f"Опрос создан. ID: {poll.poll_id}")
    except ValidationServiceError as exc:
        await message.answer(f"Ошибка: {exc}")
    finally:
        await state.clear()


@router.message(Command("list_polls"))
async def list_polls(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    polls = context.poll_service.list_polls()
    if not polls:
        await message.answer("Активных опросов нет.")
        return
    lines = []
    for poll in polls:
        days = ", ".join(poll.days) if poll.days else "-"
        lines.append(
            f"ID {poll.poll_id}: {poll.title} — {poll.schedule_type} {days} {poll.time_local.strftime('%H:%M')} "
            f"({ 'включен' if poll.is_active else 'выключен' })"
        )
    await message.answer("\n".join(lines))


@router.message(Command("toggle_poll"))
async def toggle_poll(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /toggle_poll ID (ID можно узнать через /list_polls).")
        return
    try:
        poll_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        poll = context.poll_service.get_poll(poll_id)
        updated = context.poll_service.toggle_poll(poll_id, not poll.is_active)
        await context.poll_scheduler.refresh()
        log_action(context, message.from_user.id, "toggle_poll", f"poll_id={poll_id};active={updated.is_active}")
        await message.answer(f"Опрос {poll_id} теперь {'включён' if updated.is_active else 'выключен'}.")
    except NotFoundError:
        await message.answer("Опрос не найден.")


@router.message(Command("delete_poll"))
async def delete_poll(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /delete_poll ID (ID можно узнать через /list_polls).")
        return
    try:
        poll_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        context.poll_service.delete_poll(poll_id)
        await context.poll_scheduler.refresh()
        log_action(context, message.from_user.id, "delete_poll", f"poll_id={poll_id}")
        await message.answer("Опрос удалён.")
    except NotFoundError:
        await message.answer("Опрос не найден.")


class EditPollStates(StatesGroup):
    waiting_field = State()


@router.message(Command("edit_poll"))
async def edit_poll_start(
    message: Message,
    member,
    context: BotContext,
    command: CommandObject,
    state: FSMContext,
) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    if not command.args:
        await message.answer("Использование: /edit_poll ID (ID можно узнать через /list_polls).")
        return
    try:
        poll_id = int(command.args.split()[0])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    try:
        context.poll_service.get_poll(poll_id)
    except NotFoundError:
        await message.answer("Опрос не найден.")
        return
    await state.update_data(poll_id=poll_id)
    await message.answer(
        "Отправляйте изменения в формате поле=значение. Допустимые поля: "
        "title, question, options, is_anonymous, allows_multiple_answers, schedule_type, days, "
        "time_local, target_chat_id, message_thread_id. Когда закончите — напишите «готово»."
    )
    await state.set_state(EditPollStates.waiting_field)


@router.message(EditPollStates.waiting_field)
async def edit_poll_process(message: Message, state: FSMContext, context: BotContext) -> None:
    text = message.text.strip()
    if text.lower() == "готово":
        data = await state.get_data()
        poll = context.poll_service.get_poll(data["poll_id"])
        await message.answer(f"Изменения сохранены. Статус опроса: {'включён' if poll.is_active else 'выключен'}.")
        await state.clear()
        return

    if "=" not in text:
        await message.answer("Используйте формат поле=значение или напишите «готово».")
        return

    field, value = [part.strip() for part in text.split("=", 1)]
    data = await state.get_data()
    poll = context.poll_service.get_poll(data["poll_id"])
    try:
        updated_input = _apply_field(poll, field, value)
        context.poll_service.save_poll(updated_input)
        await context.poll_scheduler.refresh()
        log_action(context, message.from_user.id, "edit_poll", f"poll_id={poll.poll_id};field={field}")
        await message.answer("Запись обновлена.")
    except (ValidationServiceError, ValueError) as exc:
        await message.answer(f"Ошибка: {exc}")


def _apply_field(poll, field: str, value: str) -> PollInput:
    data = PollInput(
        poll_id=poll.poll_id,
        title=poll.title,
        question=poll.question,
        options=poll.options,
        is_anonymous=poll.is_anonymous,
        allows_multiple_answers=poll.allows_multiple_answers,
        schedule_type=poll.schedule_type,
        days=poll.days,
        time_local=poll.time_local,
        target_chat_id=poll.target_chat_id,
        message_thread_id=poll.message_thread_id,
        is_active=poll.is_active,
    )

    if field == "title":
        data.title = value
    elif field == "question":
        data.question = value
    elif field == "options":
        options = [option.strip() for option in value.split("|") if option.strip()]
        if len(options) < 2:
            raise ValidationServiceError("Нужно минимум два варианта.")
        data.options = options
    elif field == "is_anonymous":
        data.is_anonymous = _parse_bool(value)
    elif field == "allows_multiple_answers":
        data.allows_multiple_answers = _parse_bool(value)
    elif field == "schedule_type":
        value_lower = value.lower()
        if value_lower not in {"weekly", "daily", "once"}:
            raise ValidationServiceError("Допустимые значения: weekly, daily, once.")
        data.schedule_type = value_lower
        if value_lower != "weekly":
            data.days = []
    elif field == "days":
        data.days = [day.strip().upper() for day in value.split("|") if day.strip()]
    elif field == "time_local":
        try:
            hour, minute = map(int, value.split(":"))
        except Exception as exc:  # pylint: disable=broad-except
            raise ValueError("Формат: HH:MM") from exc
        data.time_local = time(hour=hour, minute=minute)
    elif field == "target_chat_id":
        try:
            data.target_chat_id = int(value)
        except ValueError as exc:
            raise ValueError("target_chat_id должен быть числом.") from exc
    elif field == "message_thread_id":
        value = value.strip()
        data.message_thread_id = int(value) if value else None
    elif field == "is_active":
        data.is_active = _parse_bool(value)
    else:
        raise ValidationServiceError("Неизвестное поле.")

    return data
