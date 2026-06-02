from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from sqlalchemy import select

from .config import get_settings
from .database import AsyncSessionLocal
from .models import AbsenceReason, Attendance, EventResponse, JoinApplication, LearningMaterial, Normative, NormativeSubmission, Notification, ScheduleEvent, Squad, User
from .roles import RoleLevel, role_level
from .utils.audit import record_audit

logger = logging.getLogger(__name__)
router = Router(name="vpk-zvezda-db-bot")


class AbsenceReasonStates(StatesGroup):
    awaiting_custom = State()


class JoinApplicationStates(StatesGroup):
    full_name = State()
    birth_date = State()
    phone = State()
    motivation = State()
    source = State()
    confirm = State()


ROLE_LABELS = {
    "PUBLIC_USER": "Новый пользователь",
    "CANDIDATE": "Кандидат",
    "USER_PENDING": "Ожидает привязки",
    "PARTICIPANT": "Участник",
    "DEPUTY_SQUAD_COMMANDER": "Заместитель командира отделения",
    "SQUAD_COMMANDER": "Командир отделения",
    "DEPUTY_PLATOON_COMMANDER": "Заместитель командира взвода",
    "PLATOON_COMMANDER": "Командир взвода",
    "ADMIN": "Администратор",
    "SUPER_ADMIN": "Супер-администратор",
}


def parse_birth_date(value: str) -> date | None:
    text = value.strip()
    if text.casefold() in {"-", "нет", "пропустить"}:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("Invalid birth date")


async def find_user(telegram_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(User).where(User.telegram_id == telegram_id))


def user_role(user: User | None) -> RoleLevel:
    return role_level(user.role_code if user else "PUBLIC_USER")


def main_keyboard(role: RoleLevel) -> ReplyKeyboardMarkup:
    settings = get_settings()
    rows: list[list[KeyboardButton]] = [[KeyboardButton(text="Расписание"), KeyboardButton(text="Уведомления")]]
    if role >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        rows.append([KeyboardButton(text="Заявки")])
    if settings.mini_app_url:
        rows.append([KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=settings.mini_app_url))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)


def event_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Приду", callback_data=f"event:{event_id}:COMING"),
                InlineKeyboardButton(text="Не приду", callback_data=f"event:{event_id}:NOT_COMING"),
                InlineKeyboardButton(text="Уточню", callback_data=f"event:{event_id}:MAYBE"),
            ]
        ]
    )


def mini_app_keyboard() -> InlineKeyboardMarkup | None:
    settings = get_settings()
    if not settings.mini_app_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=settings.mini_app_url))]
        ]
    )


def absence_reasons_keyboard(event_id: int, reasons: list[AbsenceReason]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=reason.label, callback_data=f"reason:{event_id}:{reason.id}")]
        for reason in reasons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def save_event_response(
    *,
    event_id: int,
    user_id: int,
    response_code: str,
    absence_reason_id: int | None = None,
    custom_reason: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(EventResponse).where(EventResponse.event_id == event_id, EventResponse.user_id == user_id)
        )
        if existing is None:
            existing = EventResponse(event_id=event_id, user_id=user_id)
            session.add(existing)
        existing.response_code = response_code
        existing.absence_reason_id = absence_reason_id
        existing.custom_reason = custom_reason
        existing.responded_at = datetime.now(timezone.utc)
        existing.source_code = "BOT"
        await session.commit()


@router.message(Command("start", "menu"))
async def start(message: Message, bot: Bot) -> None:
    user = await find_user(message.from_user.id)
    role = user_role(user)

    # Handle deep link parameters
    text = message.text or ""
    if " " in text:
        param = text.split(" ", 1)[1]
        if param.startswith("view"):
            submission_id_str = param[4:]
            try:
                submission_id = int(submission_id_str)
            except (ValueError, TypeError):
                submission_id = None
            if submission_id is not None and role >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
                async with AsyncSessionLocal() as session:
                    submission = await session.get(NormativeSubmission, submission_id)
                if submission is not None:
                    comment = submission.comment or ""
                    if "[TG file_id: " in comment:
                        # Extract TG file_id from comment
                        start_idx = comment.index("[TG file_id: ") + len("[TG file_id: ")
                        end_idx = comment.find("]", start_idx)
                        tg_file_id = comment[start_idx:end_idx] if end_idx != -1 else comment[start_idx:]
                        try:
                            await bot.send_document(message.from_user.id, tg_file_id)
                        except Exception:  # noqa: BLE001
                            logger.exception("Failed to forward TG file for submission_id=%s", submission_id)
                            await message.answer("Не удалось переслать файл.", parse_mode=None)
                    elif submission.file_id is not None:
                        await message.answer("Файл загружен через приложение. Откройте Mini App для просмотра.", parse_mode=None)
                    else:
                        await message.answer("Файл для этой сдачи не найден.", parse_mode=None)
                    return
            elif submission_id is not None:
                await message.answer("Доступ только командирам.", parse_mode=None)
                return

    name = user.full_name if user else message.from_user.full_name
    role_label = ROLE_LABELS.get(user.role_code if user else "PUBLIC_USER", "Пользователь")
    lines = [
        "ВПК «Звезда»",
        "",
        f"Пользователь: {name}",
        f"Роль: {role_label}",
    ]
    if user is None:
        lines += ["", "Если вы в составе — попросите командира привязать ваш Telegram ID."]
        lines += ["Для вступления: /join"]
    await message.answer("\n".join(lines), reply_markup=main_keyboard(role), parse_mode=None)


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user is None:
        await message.answer("Профиль пока не найден. Откройте Mini App и подайте заявку или попросите командира привязать вас.")
        return
    lines = [
        user.full_name,
        f"Роль: {ROLE_LABELS.get(user.role_code, user.role_code)}",
        f"Отделение: {user.squad_id or 'не назначено'}",
        f"Статус: {user.status_code}",
    ]
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("join"))
async def join(message: Message, state: FSMContext) -> None:
    user = await find_user(message.from_user.id)
    role = user_role(user)
    if role >= RoleLevel.PARTICIPANT:
        await message.answer("Вы уже в составе. Откройте личный кабинет через Mini App.", reply_markup=mini_app_keyboard())
        return
    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(JoinApplication)
            .where(JoinApplication.telegram_id == message.from_user.id)
            .order_by(JoinApplication.id.desc())
        )
    if application:
        await message.answer(f"Ваша заявка уже есть. Статус: {application.status_code}", reply_markup=mini_app_keyboard())
    else:
        await state.set_state(JoinApplicationStates.full_name)
        await message.answer(
            "Заполним заявку прямо здесь.\n\nНапишите ФИО кандидата.",
            reply_markup=mini_app_keyboard(),
            parse_mode=None,
        )


@router.message(JoinApplicationStates.full_name)
async def join_full_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 2:
        await message.answer("ФИО слишком короткое. Напишите фамилию и имя.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(JoinApplicationStates.birth_date)
    await message.answer("Дата рождения в формате ДД.ММ.ГГГГ. Если не хотите указывать, напишите «пропустить».")


@router.message(JoinApplicationStates.birth_date)
async def join_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth_date = parse_birth_date(message.text or "")
    except ValueError:
        await message.answer("Не понял дату. Пример: 14.02.2010. Можно написать «пропустить».")
        return
    await state.update_data(birth_date=birth_date.isoformat() if birth_date else None)
    await state.set_state(JoinApplicationStates.phone)
    await message.answer("Телефон для связи. Если не хотите указывать, напишите «пропустить».")


@router.message(JoinApplicationStates.phone)
async def join_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    await state.update_data(phone=None if phone.casefold() in {"-", "нет", "пропустить"} else phone)
    await state.set_state(JoinApplicationStates.motivation)
    await message.answer("Почему хотите вступить в ВПК «Звезда»?")


@router.message(JoinApplicationStates.motivation)
async def join_motivation(message: Message, state: FSMContext) -> None:
    motivation = (message.text or "").strip()
    if len(motivation) < 3:
        await message.answer("Напишите хотя бы коротко, зачем хотите вступить.")
        return
    await state.update_data(motivation_text=motivation)
    await state.set_state(JoinApplicationStates.source)
    await message.answer("Откуда узнали о ВПК? Можно написать «пропустить».")


@router.message(JoinApplicationStates.source)
async def join_source(message: Message, state: FSMContext) -> None:
    source = (message.text or "").strip()
    await state.update_data(source_text=None if source.casefold() in {"-", "нет", "пропустить"} else source)
    data = await state.get_data()
    lines = [
        "Проверьте заявку:",
        f"ФИО: {data.get('full_name')}",
        f"Дата рождения: {data.get('birth_date') or 'не указана'}",
        f"Телефон: {data.get('phone') or 'не указан'}",
        f"Мотивация: {data.get('motivation_text')}",
        f"Источник: {data.get('source_text') or 'не указан'}",
        "",
        "Отправить заявку? Напишите «да» или «нет».",
    ]
    await state.set_state(JoinApplicationStates.confirm)
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(JoinApplicationStates.confirm)
async def join_confirm(message: Message, state: FSMContext) -> None:
    answer = (message.text or "").strip().casefold()
    if answer not in {"да", "нет"}:
        await message.answer("Напишите «да», чтобы отправить, или «нет», чтобы отменить.")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Заявка отменена. Можно начать заново командой /join.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(JoinApplication)
            .where(
                JoinApplication.telegram_id == message.from_user.id,
                JoinApplication.status_code.not_in(["REJECTED", "ARCHIVED", "ACCEPTED"]),
            )
            .order_by(JoinApplication.id.desc())
        )
        if existing:
            await state.clear()
            await message.answer(f"Активная заявка уже есть. Статус: {existing.status_code}", reply_markup=mini_app_keyboard())
            return
        user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
        application = JoinApplication(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=data["full_name"],
            birth_date=date.fromisoformat(data["birth_date"]) if data.get("birth_date") else None,
            phone=data.get("phone"),
            motivation_text=data.get("motivation_text"),
            source_text=data.get("source_text"),
            consent_given=True,
            status_code="NEW",
        )
        session.add(application)
        if user is None:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=data["full_name"],
                birth_date=application.birth_date,
                phone=application.phone,
                role_code="CANDIDATE",
                status_code="ACTIVE",
                linked_at=datetime.now(timezone.utc),
            )
            session.add(user)
        elif user.role_code == "PUBLIC_USER":
            user.full_name = data["full_name"]
            user.birth_date = application.birth_date
            user.phone = application.phone
            user.role_code = "CANDIDATE"
            user.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await record_audit(
            session,
            user_id=user.id,
            action_code="join.application.create_bot",
            entity_name="join_applications",
            entity_id=application.id,
            new_value={"telegram_id": message.from_user.id, "source": "bot"},
        )
        commanders = list((await session.scalars(
            select(User).where(
                User.status_code == "ACTIVE",
                User.role_code.in_(("PLATOON_COMMANDER", "DEPUTY_PLATOON_COMMANDER")),
            )
        )).all())
        for commander in commanders:
            session.add(Notification(
                user_id=commander.id,
                type_code="NEW_APPLICATION",
                title="Новая заявка",
                body=f"{data['full_name']} подал(а) заявку на вступление через бот.",
                entity_name="join_applications",
                entity_id=application.id,
                send_to_tg=True,
            ))
        await session.commit()
    await state.clear()
    await message.answer("Заявка отправлена. Командиры уведомлены.\nСтатус — в приложении", reply_markup=mini_app_keyboard())


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Команды бота:\n"
        "/start — главное меню\n"
        "/schedule — ближайшие занятия\n"
        "/notifications — мои уведомления\n"
        "/join — заявка на вступление\n"
        "/profile — мой профиль\n\n"
        "Все функции — в приложении",
        parse_mode=None,
    )


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.ADMIN:
        await message.answer("Команда доступна только администраторам.")
        return
    await message.answer(
        "Резервные команды:\n"
        "/broadcast текст — рассылка всем активным пользователям\n"
        "/schedule — проверить ближайшие события\n"
        "Основное управление доступно в Mini App.",
        reply_markup=mini_app_keyboard(),
        parse_mode=None,
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, bot: Bot) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.ADMIN:
        await message.answer("Команда доступна только администраторам.")
        return
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer("Использование: /broadcast текст сообщения")
        return
    async with AsyncSessionLocal() as session:
        users = list(
            (
                await session.scalars(
                    select(User).where(User.telegram_id.is_not(None), User.status_code == "ACTIVE")
                )
            ).all()
        )
    sent = 0
    for recipient in users:
        try:
            await bot.send_message(recipient.telegram_id, text)
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send broadcast to user_id=%s", recipient.id)
    await message.answer(f"Рассылка отправлена: {sent}/{len(users)}")


@router.message(Command("schedule"))
@router.message(F.text.casefold().in_({"расписание"}))
async def schedule(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Расписание доступно после подтверждения участия.")
        return
    await _send_schedule_with_batch(message, user)


@router.callback_query(F.data.startswith("event:"))
async def event_response(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректный ответ.", show_alert=True)
        return
    event_id = int(parts[1])
    response_code = parts[2]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        event = await session.get(ScheduleEvent, event_id)
        if event is None:
            await callback.answer("Событие не найдено.", show_alert=True)
            return
        if event.response_deadline_at and datetime.now(timezone.utc) > event.response_deadline_at:
            await callback.answer("Дедлайн ответа уже прошёл.", show_alert=True)
            return
        if response_code == "NOT_COMING" and event.requires_response:
            reasons = list(
                (
                    await session.scalars(
                        select(AbsenceReason).where(AbsenceReason.is_active.is_(True)).order_by(AbsenceReason.sort_order)
                    )
                ).all()
            )
            await callback.message.edit_text(
                "Выберите причину отсутствия:",
                reply_markup=absence_reasons_keyboard(event_id, reasons),
            )
            await callback.answer()
            return
    maybe_deadline: datetime | None = None
    if response_code == "MAYBE":
        async with AsyncSessionLocal() as session2:
            ev = await session2.get(ScheduleEvent, event_id)
            if ev and ev.response_deadline_at:
                maybe_deadline = ev.response_deadline_at
                reminder_at = maybe_deadline - timedelta(hours=1)
                if reminder_at > datetime.now(timezone.utc):
                    session2.add(
                        Notification(
                            user_id=user.id,
                            type_code="SCHEDULE",
                            title="Напоминание об ответе",
                            body=f"Вы ещё не дали окончательный ответ на «{ev.title}». Дедлайн: {maybe_deadline.strftime('%d.%m %H:%M')} UTC.",
                            entity_name="schedule_events",
                            entity_id=event_id,
                            send_to_tg=True,
                        )
                    )
                    await session2.commit()
    await save_event_response(event_id=event_id, user_id=user.id, response_code=response_code)
    label = {"COMING": "буду", "MAYBE": "уточню позже"}.get(response_code, "ответ сохранён")
    extra = ""
    if response_code == "MAYBE" and maybe_deadline:
        extra = f" Напомним до {maybe_deadline.strftime('%d.%m %H:%M')}."
    if callback.message:
        await callback.message.edit_text(f"Ответ записан: {label}.{extra}")
    await callback.answer("Ответ сохранён.")


@router.callback_query(F.data.startswith("reason:"))
async def absence_reason(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная причина.", show_alert=True)
        return
    event_id = int(parts[1])
    reason_id = int(parts[2])
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        reason = await session.get(AbsenceReason, reason_id)
        if reason is None:
            await callback.answer("Причина не найдена.", show_alert=True)
            return
        if reason.requires_comment:
            await state.set_state(AbsenceReasonStates.awaiting_custom)
            await state.update_data(event_id=event_id, reason_id=reason_id, user_id=user.id, reason_label=reason.label)
            await callback.message.edit_text("Напишите причину одним сообщением.")
            await callback.answer()
            return
    await save_event_response(event_id=event_id, user_id=user.id, response_code="NOT_COMING", absence_reason_id=reason_id)
    if callback.message:
        await callback.message.edit_text(f"Ответ записан: не приду. Причина: {reason.label}")
    await callback.answer("Причина сохранена.")


@router.message(AbsenceReasonStates.awaiting_custom)
async def absence_custom_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = (message.text or "").strip()
    if not text:
        await message.answer("Напишите причину текстом.")
        return
    await save_event_response(
        event_id=int(data["event_id"]),
        user_id=int(data["user_id"]),
        response_code="NOT_COMING",
        absence_reason_id=int(data["reason_id"]),
        custom_reason=text,
    )
    await state.clear()
    await message.answer(f"Ответ записан: не приду. Причина: {data.get('reason_label')}: {text}", parse_mode=None)


@router.message(Command("attendance"))
async def attendance(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Посещаемость доступна после подтверждения участия.")
        return
    STATUS_LABELS_ATT = {
        "PRESENT": "Присутствовал",
        "ABSENT": "Отсутствовал",
        "LATE": "Опоздал",
        "EXCUSED": "Уважительная",
        "SICK": "Больничный",
        "RELEASED": "Освобождён",
    }
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Attendance, ScheduleEvent.title)
            .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id, isouter=True)
            .where(Attendance.user_id == user.id)
            .order_by(Attendance.updated_at.desc())
            .limit(10)
        )
        rows = result.all()
    if not rows:
        await message.answer("Отметок посещаемости пока нет.")
        return
    lines = ["Моя посещаемость:"]
    for att, title in rows:
        date_str = att.updated_at.strftime("%d.%m") if att.updated_at else ""
        status_label = STATUS_LABELS_ATT.get(att.status_code, att.status_code)
        lines.append(f"• {title or 'Занятие'} {date_str}: {status_label}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("normatives"))
async def normatives(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Нормативы доступны после подтверждения участия.")
        return
    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(Normative)
                    .where(Normative.is_active.is_(True))
                    .where((Normative.squad_id.is_(None)) | (Normative.squad_id == user.squad_id))
                    .order_by(Normative.deadline_at.nullslast(), Normative.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
    if not rows:
        await message.answer("Активных нормативов пока нет.")
        return
    lines = ["Нормативы:"]
    for item in rows:
        deadline = item.deadline_at.strftime("%d.%m %H:%M") if item.deadline_at else "без дедлайна"
        lines.append(f"• {item.title}: {deadline}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("notifications"))
@router.message(F.text.casefold().in_({"уведомления"}))
async def notifications(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Уведомления доступны после подтверждения участия.")
        return
    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(Notification)
                    .where(Notification.user_id == user.id)
                    .order_by(Notification.is_pinned.desc(), Notification.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
    if not rows:
        await message.answer("Уведомлений пока нет.")
        return
    unread = [r for r in rows if not r.is_read]
    lines = [f"Уведомления ({len(unread)} новых):"]
    for item in rows:
        prefix = "новое:" if not item.is_read else "•"
        lines.append(f"{prefix} {item.title}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(F.text.casefold().in_({"заявки"}))
async def cmd_applications(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await message.answer("Доступ только командирам.")
        return
    async with AsyncSessionLocal() as session:
        from .models import JoinApplication
        apps = list((await session.scalars(
            select(JoinApplication)
            .where(JoinApplication.status_code.not_in(["ACCEPTED", "REJECTED", "ARCHIVED"]))
            .order_by(JoinApplication.created_at.desc())
            .limit(10)
        )).all())
    if not apps:
        await message.answer("Активных заявок нет.", reply_markup=mini_app_keyboard())
        return
    STATUS_LABELS = {
        "NEW": "Новая", "INVITED_NORMATIVES": "На нормативах",
        "REVIEWING": "На рассмотрении", "NEEDS_INFO": "Нужна информация",
    }
    lines = [f"Заявки ({len(apps)}):"]
    for app in apps:
        status = STATUS_LABELS.get(app.status_code, app.status_code)
        lines.append(f"• {app.full_name} — {status}")
    lines.append("\nДля работы с заявками откройте приложение:")
    await message.answer("\n".join(lines), reply_markup=mini_app_keyboard(), parse_mode=None)


@router.callback_query(F.data.startswith("norm_review:"))
async def normative_review_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    submission_id, status_code = int(parts[1]), parts[2]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await callback.answer("Только для командиров.", show_alert=True)
        return
    STATUS_LABELS = {"ACCEPTED": "Принято", "REJECTED": "Отклонено", "NEEDS_REDO": "На доработку"}
    status_label = STATUS_LABELS.get(status_code, status_code)
    async with AsyncSessionLocal() as session:
        submission = await session.get(NormativeSubmission, submission_id)
        if submission is None:
            await callback.answer("Сдача не найдена.", show_alert=True)
            return
        submitter = await session.get(User, submission.user_id)
        normative = await session.get(Normative, submission.normative_id)
        norm_title = normative.title if normative else f"норматив #{submission.normative_id}"
        submission.status_code = status_code
        submission.reviewed_by_id = user.id
        from datetime import datetime, timezone
        submission.reviewed_at = datetime.now(timezone.utc)
        submission.updated_at = datetime.now(timezone.utc)
        submitter_name = submitter.full_name if submitter else "участник"
        if submitter:
            body_parts = [f"Норматив: «{norm_title}»"]
            if status_code == "ACCEPTED":
                body_parts.append("Ваша сдача принята!")
            elif status_code == "REJECTED":
                body_parts.append("Ваша сдача отклонена.")
            else:
                body_parts.append("Требуется пересдача.")
            session.add(Notification(
                user_id=submitter.id,
                type_code="NORMATIVE",
                title=f"{status_label}: {norm_title}",
                body="\n".join(body_parts),
                entity_name="normative_submissions",
                entity_id=submission.id,
                send_to_tg=True,
            ))
        await session.commit()
    if callback.message:
        await callback.message.edit_text(
            f"{status_label} — {norm_title}\nУчастник: {submitter_name}",
            parse_mode=None,
        )
    await callback.answer(f"Статус: {status_label}")


# ──────────────────────── /schedule batch reply ─────────────────────────────


def batch_events_keyboard(events: list[ScheduleEvent]) -> InlineKeyboardMarkup:
    """Show 'Answer all' shortcut when there are 2+ upcoming unanswered events."""
    rows = [
        [
            InlineKeyboardButton(text="На все", callback_data="batch:COMING"),
            InlineKeyboardButton(text="Ни на одно", callback_data="batch:NOT_COMING"),
        ],
        [InlineKeyboardButton(text="По одному", callback_data="batch:ONE_BY_ONE")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("batch:"))
async def batch_response(callback: CallbackQuery) -> None:
    action = (callback.data or "").split(":")[1]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.start_datetime >= now,
                        ScheduleEvent.status_code != "CANCELLED",
                        (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == user.squad_id),
                        ScheduleEvent.requires_response.is_(True),
                    )
                    .order_by(ScheduleEvent.start_datetime)
                    .limit(7)
                )
            ).all()
        )
        if action == "ONE_BY_ONE":
            await callback.answer()
            if callback.message:
                await callback.message.delete()
            for event in events:
                start_at = event.start_datetime.strftime("%d.%m %H:%M")
                place = f"\nМесто: {event.place}" if event.place else ""
                await callback.message.answer(
                    f"{event.title}\n{start_at}{place}",
                    reply_markup=event_keyboard(event.id),
                    parse_mode=None,
                )
            return
        saved = 0
        for event in events:
            existing = await session.scalar(
                select(EventResponse).where(EventResponse.event_id == event.id, EventResponse.user_id == user.id)
            )
            if existing is None:
                existing = EventResponse(event_id=event.id, user_id=user.id)
                session.add(existing)
            existing.response_code = action
            existing.responded_at = now
            existing.source_code = "BOT"
            saved += 1
        await session.commit()
    label = "буду на всех" if action == "COMING" else "не приду ни на одно"
    if callback.message:
        await callback.message.edit_text(f"Ответ записан: {label}. Затронуто {saved} событий.")
    await callback.answer("Готово!")


# ──────────────────────── /schedule — enriched with batch ───────────────────


async def _send_schedule_with_batch(message: Message, user: User) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.start_datetime >= now,
                        (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == user.squad_id),
                    )
                    .order_by(ScheduleEvent.start_datetime)
                    .limit(7)
                )
            ).all()
        )
        if not events:
            await message.answer("Ближайших событий пока нет.")
            return
        unanswered = []
        for event in events:
            resp = await session.scalar(
                select(EventResponse).where(EventResponse.event_id == event.id, EventResponse.user_id == user.id)
            )
            if resp is None and event.requires_response:
                unanswered.append(event)
        # If 2+ unanswered events — offer batch
        if len(unanswered) >= 2:
            titles = "\n".join(
                f"• {e.title} {e.start_datetime.strftime('%d.%m %H:%M')}" for e in unanswered[:5]
            )
            await message.answer(
                f"Вы не ответили на {len(unanswered)} занятий:\n{titles}\n\nОтветить сразу на все?",
                reply_markup=batch_events_keyboard(unanswered),
                parse_mode=None,
            )
        else:
            for event in events:
                start_at = event.start_datetime.strftime("%d.%m %H:%M")
                place = f"\nМесто: {event.place}" if event.place else ""
                resp = await session.scalar(
                    select(EventResponse).where(EventResponse.event_id == event.id, EventResponse.user_id == user.id)
                )
                resp_label = ""
                if resp:
                    resp_label = {"COMING": " Вы идёте", "NOT_COMING": " Вы не идёте", "MAYBE": " Вы уточняете"}.get(resp.response_code, "")
                await message.answer(
                    f"{event.title}\n{start_at}{place}{resp_label}",
                    reply_markup=event_keyboard(event.id) if event.requires_response else None,
                    parse_mode=None,
                )


# ──────────────────────── video/photo/doc → normative ───────────────────────


class NormativeFileStates(StatesGroup):
    awaiting_normative_choice = State()


def normative_choice_keyboard(normatives: list[Normative]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=n.title[:40], callback_data=f"norm_submit:{n.id}")]
        for n in normatives[:8]
    ]
    rows.append([InlineKeyboardButton(text="Это не для норматива", callback_data="norm_submit:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.video | F.photo | F.document)
async def handle_file_message(message: Message, state: FSMContext) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        return  # silently ignore from non-participants
    async with AsyncSessionLocal() as session:
        normatives = list(
            (
                await session.scalars(
                    select(Normative)
                    .where(
                        Normative.is_active.is_(True),
                        (Normative.squad_id.is_(None)) | (Normative.squad_id == user.squad_id),
                    )
                    .order_by(Normative.deadline_at.nullslast())
                    .limit(8)
                )
            ).all()
        )
    if not normatives:
        return  # no active normatives, don't bother

    # Store file info in FSM state
    file_id: str | None = None
    if message.video:
        file_id = message.video.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id  # largest size
    elif message.document:
        file_id = message.document.file_id

    if not file_id:
        return

    await state.set_state(NormativeFileStates.awaiting_normative_choice)
    await state.update_data(file_id=file_id, user_id=user.id)
    await message.answer(
        "Это файл для сдачи норматива?\nВыберите норматив или отмените:",
        reply_markup=normative_choice_keyboard(normatives),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("norm_submit:"))
async def normative_file_submit(callback: CallbackQuery, state: FSMContext) -> None:
    norm_id_str = (callback.data or "").split(":")[1]
    if norm_id_str == "cancel":
        await state.clear()
        await callback.message.edit_text("Понял, файл не для норматива.")
        await callback.answer()
        return
    norm_id = int(norm_id_str)
    data = await state.get_data()
    file_id: str = data.get("file_id", "")
    stored_user_id: int = data.get("user_id", 0)

    user = await find_user(callback.from_user.id)
    if user is None or user.id != stored_user_id:
        await callback.answer("Ошибка сессии.", show_alert=True)
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        normative = await session.get(Normative, norm_id)
        if not normative:
            await callback.answer("Норматив не найден.", show_alert=True)
            return
        # Upsert submission with telegram_file_id stored in comment
        existing = await session.scalar(
            select(NormativeSubmission).where(
                NormativeSubmission.normative_id == norm_id,
                NormativeSubmission.user_id == user.id,
            )
        )
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = NormativeSubmission(normative_id=norm_id, user_id=user.id)
            session.add(existing)
        existing.status_code = "PENDING"
        existing.comment = f"[TG file_id: {file_id}]"
        existing.submitted_at = now
        existing.updated_at = now
        await session.flush()
        await record_audit(
            session,
            user_id=user.id,
            action_code="normative_submission.submit_via_bot",
            entity_name="normative_submissions",
            entity_id=getattr(existing, "id", 0),
            new_value={"normative_id": norm_id, "telegram_file_id": file_id, "source": "bot"},
        )
        await session.commit()
        await session.refresh(existing)
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            f"Файл принят на проверку по нормативу «{normative.title}».\nКомандир получил уведомление.",
            parse_mode=None,
        )
    await callback.answer("Сдача отправлена!")
    # Notify commanders
    async with AsyncSessionLocal() as session2:
        if user.squad_id:
            # Notify squad commanders + platoon/admin
            commander_roles = ("SQUAD_COMMANDER", "DEPUTY_SQUAD_COMMANDER", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN")
            squad_condition = (User.squad_id == user.squad_id) | User.role_code.in_(("DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN"))
        else:
            # User has no squad — notify only platoon/admin roles
            commander_roles = ("DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN")
            squad_condition = True
        commanders = list(
            (
                await session2.scalars(
                    select(User).where(
                        User.status_code == "ACTIVE",
                        User.role_code.in_(commander_roles),
                        squad_condition,
                    )
                )
            ).all()
        )
        for commander in commanders:
            session2.add(
                Notification(
                    user_id=commander.id,
                    type_code="NORMATIVE",
                    title=f"Новая сдача: {normative.title}",
                    body=f"{user.full_name} прислал файл на проверку по нормативу «{normative.title}».",
                    entity_name="normative_submissions",
                    entity_id=existing.id,
                    send_to_tg=True,
                )
            )
        await session2.commit()


# ──────────────────────── export ────────────────────────────────────────────

EXPORT_COLUMNS = [
    "ID", "Telegram ID", "Имя", "Роль", "Отделение",
    "Статус", "Телефон", "Дата рождения", "Дата привязки",
]


async def _build_export_rows(user: User) -> tuple[list[list[str]], dict[int, str]]:
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.role_code != "PUBLIC_USER").order_by(User.full_name)
        if role_level(user.role_code) < RoleLevel.DEPUTY_PLATOON_COMMANDER and user.squad_id:
            stmt = stmt.where(User.squad_id == user.squad_id)
        users = list((await session.scalars(stmt)).all())
        squads = {s.id: s.name for s in (await session.scalars(select(Squad))).all()}
    rows = []
    for u in users:
        rows.append([
            str(u.id or ""),
            str(u.telegram_id or ""),
            u.full_name or "",
            u.role_code or "",
            squads.get(u.squad_id, "—") if u.squad_id else "—",
            u.status_code or "",
            u.phone or "",
            u.birth_date.strftime("%d.%m.%Y") if u.birth_date else "",
            u.linked_at.strftime("%d.%m.%Y") if getattr(u, "linked_at", None) else "",
        ])
    return rows, squads


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await message.answer("Нет прав для экспорта данных.", parse_mode=None)
        return
    await message.answer(
        "Выберите формат экспорта состава:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Excel (.xlsx)", callback_data="export:xlsx"),
            InlineKeyboardButton(text="CSV", callback_data="export:csv"),
        ]]),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("export:"))
async def cb_export(callback: CallbackQuery, bot: Bot) -> None:
    fmt = (callback.data or "").split(":")[1]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await callback.answer("Нет прав.", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text("Формирую файл, подождите...")
    await callback.answer()

    rows, _ = await _build_export_rows(user)

    if fmt == "csv":
        buf = io.StringIO()
        buf.write("﻿")  # BOM for Excel
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(EXPORT_COLUMNS)
        for row in rows:
            writer.writerow(row)
        data = buf.getvalue().encode("utf-8")
        await bot.send_document(
            callback.from_user.id,
            BufferedInputFile(data, filename="vpk-roster.csv"),
            caption=f"Состав ВПК Звезда ({len(rows)} чел.)",
        )
    elif fmt == "xlsx":
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            await bot.send_message(callback.from_user.id, "Сервер не поддерживает XLSX. Используйте CSV.", parse_mode=None)
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Состав"
        header_fill = PatternFill(fill_type="solid", fgColor="1a2f5a")
        header_font = Font(color="FFFFFF", bold=True)
        ws.append(EXPORT_COLUMNS)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for row in rows:
            ws.append(row)
        buf_b = io.BytesIO()
        wb.save(buf_b)
        buf_b.seek(0)
        await bot.send_document(
            callback.from_user.id,
            BufferedInputFile(buf_b.read(), filename="vpk-roster.xlsx"),
            caption=f"Состав ВПК Звезда ({len(rows)} чел.)",
        )

    if callback.message:
        await callback.message.edit_text(f"Файл отправлен ({len(rows)} участников).")


# ──────────────────────── inline mode ───────────────────────────────────────


@router.inline_query()
async def inline_schedule(query: InlineQuery) -> None:
    """@vpkbot [текст] — показать расписание в любом чате."""
    user = await find_user(query.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await query.answer(
            [InlineQueryResultArticle(
                id="no_access",
                title="Нет доступа",
                input_message_content=InputTextMessageContent(message_text="Сначала зарегистрируйтесь в ВПК «Звезда»."),
            )],
            cache_time=10,
        )
        return

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.start_datetime >= now,
                        (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == user.squad_id),
                        ScheduleEvent.status_code != "CANCELLED",
                    )
                    .order_by(ScheduleEvent.start_datetime)
                    .limit(5)
                )
            ).all()
        )

    results = []
    for event in events:
        start_str = event.start_datetime.strftime("%d.%m %H:%M")
        place_str = f" · {event.place}" if event.place else ""
        text = f"{event.title}\n{start_str}{place_str}"
        results.append(
            InlineQueryResultArticle(
                id=str(event.id),
                title=f"{event.title}",
                description=f"{start_str}{place_str}",
                input_message_content=InputTextMessageContent(message_text=text),
            )
        )
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="empty",
                title="Событий нет",
                input_message_content=InputTextMessageContent(message_text="Ближайших событий не запланировано."),
            )
        )
    await query.answer(results, cache_time=60)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if settings.dryrun:
        logger.info("Starting VPK Zvezda Telegram bot in DRYRUN mode; polling is disabled")
        await asyncio.Event().wait()
    bot = Bot(settings.bot_token)
    if settings.mini_app_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть приложение",
                web_app=WebAppInfo(url=settings.mini_app_url),
            )
        )
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="schedule", description="Расписание занятий"),
        BotCommand(command="notifications", description="Мои уведомления"),
        BotCommand(command="join", description="Заявка на вступление"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="export", description="Выгрузка состава (CSV/Excel)"),
        BotCommand(command="help", description="Помощь"),
    ])
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    logger.info("Starting VPK Zvezda Telegram bot")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
