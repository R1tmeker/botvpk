from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
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
from sqlalchemy import or_, select

from .config import get_settings
from .database import AsyncSessionLocal
from .models import AbsenceReason, Appeal, AppealMessage, Attendance, EventResponse, JoinApplication, Normative, NormativeSubmission, Notification, ScheduleEvent, Squad, User
from .roles import RoleLevel, role_level
from .services.auth_security import PasswordPolicyError, bump_token_version, validate_password_policy
from .services.appeal_policy import APPEAL_STATUS_LABELS, can_access_appeal, validate_appeal_text
from .services.appeals import add_appeal_reply, notify_appeal_commanders, publish_appeal_update
from .services.bot_callbacks import callback_ids
from .services.bot_navigation import MENU_TEXT, entity_id, menu_rows, page_number
from .services.bot_content import attendance_text, checkin_statement, local_time, normative_choices, normatives_text, schedule_card
from .services.attendance import SelfCheckInError, self_check_in, sync_automatic_grade
from .services.delivery import call_telegram_with_rate_limit
from .services.events import respond_to_event
from .services.join_input import join_text, normalize_join_phone, parse_join_birth_date as parse_birth_date
from .services.event_response_policy import EventResponseError, validate_event_available
from .services.notification_inbox import inbox_counts, inbox_page, mark_inbox_read, mark_notification_read
from .services.search import search_accessible
from .services.realtime import publish_realtime_event
from .services.heartbeat import heartbeat_loop
from .services.observability import configure_json_logging, init_sentry
from .services.normatives import submit_normative as submit_normative_service
from .utils.audit import record_audit
from .utils.channel_link import issue_link_code
from .utils.password import hash_password

logger = logging.getLogger(__name__)
router = Router(name="vpk-zvezda-db-bot")

_CF_URL_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com')
_CF_LOG_PATH = "/tmp/cf_tunnel.log"
JOIN_STATE_TIMEOUT = timedelta(days=1)
INBOX_PAGE_SIZE = 6
ATTENDANCE_PAGE_SIZE = 8


def _detect_tunnel_url() -> str | None:
    try:
        with open(_CF_LOG_PATH) as f:
            content = f.read()
        matches = _CF_URL_RE.findall(content)
        return matches[-1] if matches else None
    except OSError:
        return None


class SearchStates(StatesGroup):
    query = State()


class AbsenceReasonStates(StatesGroup):
    awaiting_custom = State()


class JoinApplicationStates(StatesGroup):
    full_name = State()
    birth_date = State()
    phone = State()
    motivation = State()
    source = State()
    confirm = State()


class AppealStates(StatesGroup):
    subject = State()
    description = State()
    urgency = State()


class AppealReplyStates(StatesGroup):
    body = State()


class PasswordResetStates(StatesGroup):
    new_password = State()
    confirm_password = State()


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

PARTICIPANT_ROLE_CODES = (
    "PARTICIPANT",
    "DEPUTY_SQUAD_COMMANDER",
    "SQUAD_COMMANDER",
    "DEPUTY_PLATOON_COMMANDER",
    "PLATOON_COMMANDER",
    "ADMIN",
    "SUPER_ADMIN",
)


async def find_user(telegram_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(User).where(User.telegram_id == telegram_id))


def user_role(user: User | None) -> RoleLevel:
    return role_level(user.role_code if user and user.status_code == "ACTIVE" else "PUBLIC_USER")


def main_keyboard(role: RoleLevel) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Меню")]]
    if role >= RoleLevel.PARTICIPANT:
        rows[0].append(KeyboardButton(text="Отметиться"))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Назад"), KeyboardButton(text="Отмена")], [KeyboardButton(text="Меню")]], resize_keyboard=True)


def main_menu_inline(role: RoleLevel, section: str = "home") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"menu:{action}") for label, action in row]
            for row in menu_rows(role, section)]
    settings = get_settings()
    if settings.mini_app_url and section == "home":
        rows.append([InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=settings.mini_app_url))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def home_button(parent: str = "home") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="← Назад", callback_data=f"menu:{parent}")] + ([InlineKeyboardButton(text="Главное меню", callback_data="menu:home")] if parent != "home" else [])


def event_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Приду", callback_data=f"event:{event_id}:COMING"),
                InlineKeyboardButton(text="Не приду", callback_data=f"event:{event_id}:NOT_COMING"),
            ],
            [InlineKeyboardButton(text="Уточню", callback_data=f"event:{event_id}:MAYBE")],
            [InlineKeyboardButton(text="← К расписанию", callback_data="menu:schedule")],
        ]
    )


def mini_app_keyboard() -> InlineKeyboardMarkup | None:
    settings = get_settings()
    rows = [[InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=settings.mini_app_url))]] if settings.mini_app_url else []
    return InlineKeyboardMarkup(inline_keyboard=[*rows, home_button()])


def absence_reasons_keyboard(event_id: int, reasons: list[AbsenceReason]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=reason.label, callback_data=f"reason:{event_id}:{reason.id}")]
        for reason in reasons
    ]
    rows.append([InlineKeyboardButton(text="← К расписанию", callback_data="menu:schedule")])
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
        user = await session.get(User, user_id)
        event = await session.scalar(select(ScheduleEvent).where(ScheduleEvent.id == event_id).with_for_update())
        if user is None or user.status_code != "ACTIVE":
            raise EventResponseError("FORBIDDEN", "Нужна активная привязка к составу.")
        if event is None:
            raise EventResponseError("NOT_FOUND", "Занятие не найдено. Обновите расписание.")
        await respond_to_event(
            session, event=event, user_id=user.id, role=user_role(user), squad_id=user.squad_id,
            response_code=response_code, absence_reason_id=absence_reason_id, custom_reason=custom_reason, source_code="BOT",
        )
        await record_audit(
            session, user_id=user.id, action_code="schedule_event.respond", entity_name="schedule_events",
            entity_id=event_id, new_value={"response_code": response_code, "source_code": "BOT"},
        )
        await session.commit()
    await publish_realtime_event(
        get_settings(), event_type="schedule.response.updated", user_id=user_id, query_keys=["schedule", "dashboard"],
    )


async def ensure_dialog_not_expired(message: Message, state: FSMContext) -> bool:
    data = await state.get_data()
    started_at_raw = data.get("started_at")
    if not started_at_raw:
        return False
    try:
        started_at = datetime.fromisoformat(started_at_raw)
    except (TypeError, ValueError):
        return False
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - started_at <= JOIN_STATE_TIMEOUT:
        return False
    await state.clear()
    await message.answer("Диалог устарел и был сброшен. Начните заново нужной командой.", parse_mode=None)
    return True


async def show_main_menu(message: Message, user: User | None = None) -> None:
    user = user or await find_user(message.from_user.id)
    role = user_role(user)
    await message.answer(MENU_TEXT["home"] if role >= RoleLevel.PARTICIPANT else "Добро пожаловать! Вступление и помощь:", reply_markup=main_menu_inline(role), parse_mode=None)


@router.message(Command("start", "menu"))
async def start(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.clear()
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
    lines = ["ВПК «Звезда»", name]
    if role < RoleLevel.PARTICIPANT:
        lines.append("Если вы уже в составе — передайте командиру ваш Telegram ID из меню.")
    await message.answer("\n".join(lines), reply_markup=main_keyboard(role), parse_mode=None)
    await show_main_menu(message, user)


@router.message(F.text.casefold().in_({"меню"}))
async def menu_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_main_menu(message)


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user is None:
        await message.answer("Профиль пока не найден. Откройте Mini App и подайте заявку или попросите командира привязать вас.")
        return
    await send_profile(message, user)


async def send_profile(message: Message, user: User) -> None:
    lines = [
        user.full_name,
        f"Должность: {ROLE_LABELS.get(user.role_code, user.role_code)}",
        f"Отделение: {user.squad_id or 'не назначено'}",
        f"Статус: {user.status_code}",
    ]
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button("personal")]), parse_mode=None)


@router.message(Command("id"))
@router.message(F.text.casefold().in_({"мой id", "мой айди", "id"}))
async def my_telegram_id(message: Message) -> None:
    await send_telegram_id(message, message.from_user.id)


async def send_telegram_id(message: Message, telegram_id: int) -> None:
    await message.answer(
        f"Ваш Telegram ID: <code>{telegram_id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button("account" if user_role(await find_user(telegram_id)) >= RoleLevel.PARTICIPANT else "home")]),
    )


@router.message(F.text == "Ссылка туннеля")
async def tunnel_url(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.SUPER_ADMIN:
        return
    url = _detect_tunnel_url()
    settings = get_settings()
    lines: list[str] = []
    if url:
        lines.append(f"Текущий URL туннеля:\n{url}")
    else:
        lines.append("URL туннеля не найден в логах cf-tunnel.")
    env_url = settings.mini_app_url
    if env_url and env_url != url:
        lines.append(f"\nВ .env сейчас другой URL:\n{env_url}")
    elif env_url:
        lines.append("\nСовпадает с MINI_APP_URL в .env")
    reply_markup = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть Mini App", web_app=WebAppInfo(url=url))]
            ]
        )
        if url
        else mini_app_keyboard()
    )
    await message.answer("\n".join(lines), reply_markup=reply_markup, parse_mode=None)


@router.message(Command("cancel"))
@router.message(F.text.casefold().in_({"отмена", "cancel", "стоп"}))
async def cancel_dialog(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    await state.clear()
    user = await find_user(message.from_user.id)
    reply_markup = main_keyboard(user_role(user))
    if current_state:
        await message.answer("Действие отменено.", reply_markup=reply_markup, parse_mode=None)
        await show_main_menu(message, user)
    else:
        await message.answer("Активного диалога нет. Открыл меню.", reply_markup=reply_markup, parse_mode=None)
        await show_main_menu(message, user)



@router.message(Command("back"))
@router.message(F.text.casefold().in_({"назад", "← назад"}))
async def dialog_back(message: Message, state: FSMContext) -> None:
    await go_back(message, state, message.from_user.id)


@router.callback_query(F.data == "dialog:back")
async def dialog_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await go_back(callback.message, state, callback.from_user.id)


async def go_back(message: Message, state: FSMContext, telegram_id: int) -> None:
    current = await state.get_state()
    data = await state.get_data()
    if current and await ensure_dialog_not_expired(message, state):
        return
    if current in [item.state for item in JOIN_STEPS] and current != JoinApplicationStates.full_name.state:
        await join_back(message, state, telegram_id)
        return
    if current == AppealStates.description.state:
        await state.set_state(AppealStates.subject)
        await message.answer(f"Тема обращения. Ранее: {data.get('subject', '')}\nНапишите новое значение или повторите прежнее.", reply_markup=cancel_keyboard(), parse_mode=None)
        return
    if current == AppealStates.urgency.state:
        await state.set_state(AppealStates.description)
        await message.answer(f"Описание обращения. Ранее: {str(data.get('description', ''))[:2500]}\nНапишите новое значение или повторите прежнее.", reply_markup=cancel_keyboard(), parse_mode=None)
        return
    if current == PasswordResetStates.confirm_password.state:
        await state.update_data(new_password=None)
        await state.set_state(PasswordResetStates.new_password)
        await message.answer("Введите новый пароль заново.", reply_markup=cancel_keyboard(), parse_mode=None)
        return
    user = await find_user(telegram_id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await state.clear()
        await show_main_menu(message, user)
        return
    if current == AppealReplyStates.body.state:
        await state.clear()
        await send_appeal_thread(message, user, data.get("appeal_id", 0))
        return
    if current == AbsenceReasonStates.awaiting_custom.state:
        async with AsyncSessionLocal() as session:
            event = await session.get(ScheduleEvent, data.get("event_id"))
            reasons = list((await session.scalars(select(AbsenceReason).where(AbsenceReason.is_active.is_(True)).order_by(AbsenceReason.sort_order))).all())
        await state.clear()
        if event:
            await message.answer(f"Причина отсутствия на «{event.title}»:", reply_markup=absence_reasons_keyboard(event.id, reasons), parse_mode=None)
        else:
            await _send_schedule_with_batch(message, user)
        return
    if current == NormativeFileStates.awaiting_normative_choice.state:
        await send_normatives_text(message, user)
        await message.answer("Ранее присланный файл сохранён. Можно вернуться к выбору или прислать другой.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Выбрать для файла", callback_data="normchoicepage:0")], home_button()]), parse_mode=None)
        return
    parent = "contact" if current == AppealStates.subject.state else "account" if current == PasswordResetStates.new_password.state else "personal" if current == SearchStates.query.state else "home"
    await state.clear()
    await message.answer(MENU_TEXT[parent], reply_markup=main_menu_inline(user_role(user), parent), parse_mode=None)


def app_deep_link(path: str | None) -> str | None:
    from urllib.parse import urljoin, urlsplit
    base = get_settings().mini_app_url
    if not base or not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return None
    result = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    return result if urlsplit(result).scheme == "https" else None


@router.message(Command("search"))
@router.message(F.text.casefold().in_({"поиск"}))
async def search_command(message: Message, state: FSMContext) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Поиск доступен после подтверждения участия.")
        return
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        await state.clear()
        await state.set_state(SearchStates.query)
        await state.update_data(started_at=datetime.now(timezone.utc).isoformat())
        await message.answer("Что найти? Напишите от 2 до 100 символов: название занятия, норматива, материала или имя участника.", reply_markup=cancel_keyboard(), parse_mode=None)
        return
    await send_search_results(message, user, query)


async def send_search_results(message: Message, user: User, query: str) -> None:
    if not 2 <= len(query) <= 100:
        await message.answer("Напишите от 2 до 100 символов.", parse_mode=None)
        return
    async with AsyncSessionLocal() as session:
        results = await search_accessible(session, query, role=user_role(user), role_code=user.role_code, squad_id=user.squad_id, user_id=user.id, limit=10)
    if not results:
        await message.answer("По вашему запросу ничего доступного не найдено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button("personal")]))
        return
    labels = {"event": "Занятие", "normative": "Норматив", "material": "Материал", "appeal": "Обращение", "person": "Участник"}
    lines = [f"Найдено по запросу «{query}»:"]
    buttons = []
    for number, item in enumerate(results, start=1):
        lines.append(f"{number}. {labels[item.type]}: {item.title[:180]}")
        if item.description:
            lines.append(item.description[:150])
        url = app_deep_link(item.deep_link)
        if url:
            buttons.append([InlineKeyboardButton(text=f"{number}. {item.title[:45]}", web_app=WebAppInfo(url=url))])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[*buttons, home_button("personal")]), parse_mode=None)

@router.message(SearchStates.query)
async def search_query(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    query = (message.text or "").strip()
    if query.startswith("/") or not 2 <= len(query) <= 100:
        await message.answer("Напишите поисковый запрос от 2 до 100 символов или нажмите «Отмена».")
        return
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await state.clear()
        await message.answer("Поиск доступен участникам состава.")
        return
    await state.clear()
    await send_search_results(message, user, query)



JOIN_STEPS = [JoinApplicationStates.full_name, JoinApplicationStates.birth_date, JoinApplicationStates.phone,
              JoinApplicationStates.motivation, JoinApplicationStates.source, JoinApplicationStates.confirm]


def join_keyboard(*, phone: bool = False, private: bool = True) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Назад"), KeyboardButton(text="Отмена")]]
    if phone and private:
        rows.insert(0, [KeyboardButton(text="Поделиться своим телефоном", request_contact=True)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def prompt_join_step(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    data = await state.get_data()
    prompts = {
        JoinApplicationStates.full_name.state: ("ФИО кандидата (от 2 до 255 символов).", "full_name"),
        JoinApplicationStates.birth_date.state: ("Дата рождения в формате ДД.ММ.ГГГГ или «пропустить».", "birth_date"),
        JoinApplicationStates.phone.state: ("Телефон с кодом страны, например +7 999 123-45-67, или «пропустить».", "phone"),
        JoinApplicationStates.motivation.state: ("Почему хотите вступить в ВПК «Звезда»? От 3 до 1500 символов.", "motivation_text"),
        JoinApplicationStates.source.state: ("Откуда узнали о ВПК? До 300 символов или «пропустить».", "source_text"),
    }
    if current == JoinApplicationStates.confirm.state:
        lines = ["Проверьте заявку:", f"ФИО: {data.get('full_name')}",
                 f"Дата рождения: {data.get('birth_date') or 'не указана'}",
                 f"Телефон: {data.get('phone') or 'не указан'}", f"Мотивация: {data.get('motivation_text')}",
                 f"Источник: {data.get('source_text') or 'не указан'}", "",
                 "Напишите «да», чтобы отправить заявку и дать согласие на обработку указанных персональных данных для её рассмотрения ВПК «Звезда».",
                 "«Назад» или /back — исправить данные. «Нет» или /cancel — отменить."]
        text = "\n".join(lines)
    else:
        prompt, field = prompts.get(current, prompts[JoinApplicationStates.full_name.state])
        text = prompt
        if data.get(field):
            text += f"\nРанее указано: {data[field]}\nВведите новое значение или отправьте прежнее ещё раз."
    step = next((i + 1 for i, item in enumerate(JOIN_STEPS) if item.state == current), 1)
    await message.answer(f"Шаг {step}/{len(JOIN_STEPS)}\n{text}",
                         reply_markup=join_keyboard(phone=current == JoinApplicationStates.phone.state, private=message.chat.type == "private"), parse_mode=None)


async def join_back(message: Message, state: FSMContext, telegram_id: int | None = None) -> None:
    current = await state.get_state()
    states = [item.state for item in JOIN_STEPS]
    if current not in states:
        await message.answer("Возврат по шагам доступен во время заполнения /join.", parse_mode=None)
        return
    if await ensure_dialog_not_expired(message, state):
        return
    if current == states[0]:
        await state.clear()
        await show_main_menu(message, await find_user(telegram_id or message.from_user.id))
        return
    await state.set_state(JOIN_STEPS[max(0, states.index(current) - 1)])
    await prompt_join_step(message, state)


@router.message(Command("join"))
async def join(message: Message, state: FSMContext) -> None:
    await start_join_dialog(message, state, message.from_user.id)


async def start_join_dialog(message: Message, state: FSMContext, telegram_id: int) -> None:
    user = await find_user(telegram_id)
    if user_role(user) >= RoleLevel.PARTICIPANT:
        await message.answer("Вы уже в составе. Откройте личный кабинет через Mini App.", reply_markup=mini_app_keyboard())
        return
    current = await state.get_state()
    if current in [item.state for item in JOIN_STEPS] and not await ensure_dialog_not_expired(message, state):
        await message.answer("Продолжаем вашу анкету. Данные предыдущих шагов сохранены.", parse_mode=None)
        await prompt_join_step(message, state)
        return
    if current and current not in [item.state for item in JOIN_STEPS]:
        await message.answer("Завершите текущий диалог или отмените его командой /cancel, затем используйте /join.", parse_mode=None)
        return
    async with AsyncSessionLocal() as session:
        application = await session.scalar(select(JoinApplication).where(
            JoinApplication.telegram_id == telegram_id,
            JoinApplication.status_code.not_in(["REJECTED", "ARCHIVED"]),
        ).order_by(JoinApplication.id.desc()))
    if application:
        await message.answer(f"Ваша заявка уже есть. Статус: {application.status_code}", reply_markup=mini_app_keyboard())
        return
    await state.clear()
    await state.set_state(JoinApplicationStates.full_name)
    await state.update_data(started_at=datetime.now(timezone.utc).isoformat())
    await message.answer("Заполним заявку здесь. Для исправления предыдущего поля — /back, для отмены — /cancel.", parse_mode=None)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.full_name)
async def join_full_name(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    try:
        full_name = join_text(" ".join((message.text or "").split()), label="ФИО", minimum=2, maximum=255)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(full_name=full_name)
    await state.set_state(JoinApplicationStates.birth_date)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.birth_date)
async def join_birth_date(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    try:
        birth_date = parse_birth_date(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(birth_date=birth_date.isoformat() if birth_date else None)
    await state.set_state(JoinApplicationStates.phone)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.phone)
async def join_phone(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    if message.contact and message.contact.user_id != message.from_user.id:
        await message.answer("Поделитесь своим контактом или укажите телефон текстом.", parse_mode=None)
        return
    try:
        phone = normalize_join_phone(message.contact.phone_number if message.contact else message.text)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(phone=phone)
    await state.set_state(JoinApplicationStates.motivation)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.motivation)
async def join_motivation(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    try:
        motivation = join_text(message.text or "", label="Мотивация", minimum=3, maximum=1500)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(motivation_text=motivation)
    await state.set_state(JoinApplicationStates.source)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.source)
async def join_source(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    try:
        source = join_text(message.text or "", label="Источник", maximum=300, optional=True)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(source_text=source)
    await state.set_state(JoinApplicationStates.confirm)
    await prompt_join_step(message, state)


@router.message(JoinApplicationStates.confirm)
async def join_confirm(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    answer = (message.text or "").strip().casefold()
    if answer not in {"да", "нет"}:
        await message.answer("Напишите «да», чтобы отправить, или «нет», чтобы отменить.")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Заявка отменена. Можно начать заново командой /join.", reply_markup=main_keyboard(RoleLevel.PUBLIC_USER))
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
    await message.answer(
        "Заявка отправлена. Командиры уведомлены.\nСтатус — в приложении",
        reply_markup=main_keyboard(RoleLevel.CANDIDATE),
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Помощь по боту ВПК «Звезда»:\n\n"
        "/start или /menu — главное меню.\n"
        "/schedule — ближайшие занятия. Под уведомлением о занятии нажмите «Приду», «Не приду» или «Пока не знаю».\n"
        "/normatives — активные нормативы. Чтобы сдать норматив, просто пришлите фото, видео или документ в бот и выберите норматив.\n"
        "/attendance — ваши отметки посещаемости.\n"
        "/notifications — уведомления, текст, страницы и отметка прочтения.\n"
        "/search текст — поиск занятий, нормативов, материалов и обращений.\n"
        "/appeal — обращение командиру без Mini App.\n"
        "/myappeals — обращения по страницам и переписка.\n"
        "/appealview номер — открыть обращение и ответить прямо здесь.\n"
        "/vk — код для привязки ВКонтакте.\n"
        "/resetpassword — код сброса и смена пароля через Telegram.\n"
        "/back — исправить предыдущий шаг анкеты. /join продолжает начатую анкету.\n"
        "/join — заявка на вступление.\n"
        "/profile — ваш профиль.\n"
        "/cancel — отменить текущий диалог.\n\n"
        "Командирам доступны заявки, экспорт состава, проверка нормативов и отметка явки через кнопки в уведомлениях.",
        parse_mode=None,
    )


@router.message(Command("vk"))
async def vk_link(message: Message) -> None:
    await send_vk_link_code(message, message.from_user.id)


async def send_vk_link_code(message: Message, telegram_id: int) -> None:
    user = await find_user(telegram_id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Привязка VK доступна подтверждённым участникам состава.", parse_mode=None)
        return
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is None:
            await message.answer("Профиль не найден. Обратитесь к командиру.", parse_mode=None)
            return
        code, expires_at = await issue_link_code(session, db_user.id, channel="VK")
        await record_audit(
            session,
            user_id=db_user.id,
            action_code="vk.link_code.issue_bot",
            entity_name="users",
            entity_id=db_user.id,
        )
        await session.commit()
    settings = get_settings()
    lines = [
        "Код привязки VK:",
        code,
        "",
        f"Действует до {expires_at.strftime('%d.%m %H:%M')} UTC.",
        "Отправьте этот код в VK-бот одним сообщением.",
    ]
    if settings.vk_bot_url:
        lines.append(f"\nVK-бот: {settings.vk_bot_url}")
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button("account")]), parse_mode=None)


@router.message(Command("resetpassword"))
async def reset_password_start(message: Message, state: FSMContext) -> None:
    await start_password_dialog(message, state, message.from_user.id)


async def start_password_dialog(message: Message, state: FSMContext, telegram_id: int) -> None:
    user = await find_user(telegram_id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Сброс пароля доступен подтверждённым участникам состава.", parse_mode=None)
        return
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is None:
            await message.answer("Профиль не найден. Обратитесь к командиру.", parse_mode=None)
            return
        code, expires_at = await issue_link_code(session, db_user.id, channel="PASSWORD_RESET")
        await record_audit(
            session,
            user_id=db_user.id,
            action_code="auth.password.reset_code.issue_bot",
            entity_name="users",
            entity_id=db_user.id,
        )
        await session.commit()
    await state.set_state(PasswordResetStates.new_password)
    await state.update_data(started_at=datetime.now(timezone.utc).isoformat(), user_id=user.id)
    await message.answer(
        "Код сброса пароля для входа на сайте:\n"
        f"{code}\n\n"
        f"Действует до {expires_at.strftime('%d.%m %H:%M')} UTC.\n"
        "Можно ввести код на странице входа или задать новый пароль прямо здесь: напишите новый пароль.",
        reply_markup=cancel_keyboard(),
        parse_mode=None,
    )


@router.message(PasswordResetStates.new_password)
async def reset_password_new_password(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    password = (message.text or "").strip()
    user = await find_user(message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("Профиль не найден. Обратитесь к командиру.", parse_mode=None)
        return
    try:
        validate_password_policy(password, telegram_id=user.telegram_id)
    except PasswordPolicyError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.update_data(new_password=password)
    await state.set_state(PasswordResetStates.confirm_password)
    await message.answer("Повторите новый пароль для подтверждения.", reply_markup=cancel_keyboard(), parse_mode=None)


@router.message(PasswordResetStates.confirm_password)
async def reset_password_confirm(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    data = await state.get_data()
    password = str(data.get("new_password") or "")
    if (message.text or "").strip() != password:
        await state.set_state(PasswordResetStates.new_password)
        await state.update_data(new_password=None)
        await message.answer("Пароли не совпали. Напишите новый пароль ещё раз.", reply_markup=cancel_keyboard())
        return
    user_id = int(data.get("user_id") or 0)
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            await state.clear()
            await message.answer("Профиль не найден. Обратитесь к командиру.", parse_mode=None)
            return
        user.password_hash = hash_password(password)
        user.password_set_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        user.failed_login_count = 0
        user.locked_until = None
        bump_token_version(user)
        await record_audit(
            session,
            user_id=user.id,
            action_code="auth.password.reset_bot",
            entity_name="users",
            entity_id=user.id,
        )
        await session.commit()
    await state.clear()
    await message.answer("Пароль обновлён. Старые сессии сайта отозваны.", reply_markup=main_keyboard(user_role(user)), parse_mode=None)


@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    action = (callback.data or "").split(":", 1)[1]
    message = callback.message
    if message is None:
        await callback.answer()
        return
    user = await find_user(callback.from_user.id)
    role = user_role(user)
    await state.clear()
    if action in MENU_TEXT:
        text = MENU_TEXT[action] if role >= RoleLevel.PARTICIPANT else "Добро пожаловать! Вступление и помощь:"
        try:
            await message.edit_text(text, reply_markup=main_menu_inline(role, action), parse_mode=None)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await message.answer(text, reply_markup=main_menu_inline(role, action), parse_mode=None)
        await callback.answer()
        return
    if action == "profile" and user is not None and role >= RoleLevel.PARTICIPANT:
        await send_profile(message, user)
    elif action in {"applications", "journal", "admin"}:
        if role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
            await callback.answer("Доступ только командирам.", show_alert=True)
            return
        if action == "applications":
            await send_applications(message)
        else:
            path = "/attendance" if action == "journal" else "/admin"
            url = app_deep_link(path)
            buttons = [[InlineKeyboardButton(text="Открыть раздел", web_app=WebAppInfo(url=url))]] if url else []
            await message.answer("Журнал явки также доступен через кнопки в напоминаниях о занятии." if action == "journal" else "Управление составом и настройками:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[*buttons, home_button("command")]), parse_mode=None)
    elif action == "password":
        await start_password_dialog(message, state, callback.from_user.id)
    elif action == "help":
        await message.answer("Расписание — ваши планы, самоотметка — присутствие. Пришлите фото, видео или документ для сдачи норматива. Связь — обращения и ответы командира. Меню возвращает сюда и отменяет текущий ввод.", reply_markup=main_menu_inline(role), parse_mode=None)
    elif action == "schedule":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Расписание доступно после подтверждения участия.")
        else:
            await _send_schedule_with_batch(message, user)
    elif action == "notifications":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Уведомления доступны после подтверждения участия.")
        else:
            await send_notifications_text(message, user)
    elif action == "search":
        if role < RoleLevel.PARTICIPANT:
            await callback.answer("Поиск доступен участникам.", show_alert=True)
            return
        await state.set_state(SearchStates.query)
        await state.update_data(started_at=datetime.now(timezone.utc).isoformat())
        await message.answer("Что найти? Напишите от 2 до 100 символов.", reply_markup=cancel_keyboard(), parse_mode=None)
    elif action == "normatives":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Нормативы доступны после подтверждения участия.")
        else:
            await send_normatives_text(message, user)
    elif action == "attendance":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Посещаемость доступна после подтверждения участия.")
        else:
            await send_attendance_text(message, user)
    elif action == "checkin":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Самоотметка доступна после подтверждения участия.")
        else:
            await send_self_checkin_result(message, user)
    elif action == "myappeals":
        if user is None or role < RoleLevel.PARTICIPANT:
            await message.answer("Обращения доступны после подтверждения участия.")
        else:
            await send_my_appeals(message, user)
    elif action == "appeal":
        await start_appeal_dialog(message, state, callback.from_user.id)
    elif action == "vk":
        await send_vk_link_code(message, callback.from_user.id)
    elif action == "join":
        await start_join_dialog(message, state, callback.from_user.id)
    elif action == "my_id":
        await send_telegram_id(message, callback.from_user.id)
    else:
        await callback.answer("Раздел пока недоступен.", show_alert=True)
        return
    await callback.answer()


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
            await call_telegram_with_rate_limit(lambda recipient=recipient: bot.send_message(recipient.telegram_id, text))
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


async def send_self_checkin_result(message: Message, user: User, event_id: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list((await session.scalars(checkin_statement(user, now, event_id))).all())
        if len(events) > 1:
            rows = [[InlineKeyboardButton(text=f"{local_time(event.start_datetime)} · {event.title[:30]}", callback_data=f"selfcheckin:{event.id}")] for event in events]
            await message.answer("На каком занятии вы присутствуете?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[*rows, home_button()]), parse_mode=None)
            return
        last_error: SelfCheckInError | None = None
        for event in events:
            try:
                attendance_row, created = await self_check_in(
                    session,
                    event=event,
                    user_id=user.id,
                    now=now,
                    source_code="BOT",
                )
            except SelfCheckInError as exc:
                last_error = exc
                continue
            if created:
                await sync_automatic_grade(
                    session=session,
                    event=event,
                    attendance=attendance_row,
                    actor_id=user.id,
                )
                await record_audit(
                    session,
                    user_id=user.id,
                    action_code="attendance.self_checkin_bot",
                    entity_name="attendance",
                    entity_id=attendance_row.id,
                    new_value={"event_id": event.id, "status_code": attendance_row.status_code, "source_code": "BOT"},
                )
            await session.commit()
            status_label = "опоздание" if attendance_row.status_code == "LATE" else "присутствие"
            await message.answer(f"{event.title}: {status_label} отмечено.", reply_markup=main_keyboard(user_role(user)))
            return
    detail = str(last_error) if last_error else "Сейчас нет события с открытым окном самоотметки."
    await message.answer(detail, reply_markup=main_keyboard(user_role(user)))


@router.callback_query(F.data.startswith("selfcheckin:"))
async def self_checkin_callback(callback: CallbackQuery) -> None:
    ids = callback_ids(callback.data, "selfcheckin", 1)
    user = await find_user(callback.from_user.id)
    if ids is None or user is None or user_role(user) < RoleLevel.PARTICIPANT or callback.message is None:
        await callback.answer("Самоотметка недоступна.", show_alert=True)
        return
    await callback.answer()
    await send_self_checkin_result(callback.message, user, ids[0])


@router.message(Command("checkin"))
@router.message(F.text.casefold().in_({"отметиться", "самоотметка"}))
async def self_checkin_command(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Самоотметка доступна после подтверждения участия.")
        return
    await send_self_checkin_result(message, user)


def bot_event_time(value: datetime) -> str:
    return local_time(value)


@router.callback_query(F.data.startswith("event:"))
async def event_response(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in {"COMING", "NOT_COMING", "MAYBE"}:
        await callback.answer("Некорректный ответ.", show_alert=True)
        return
    event_id, response_code = int(parts[1]), parts[2]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    try:
        async with AsyncSessionLocal() as session:
            event = await session.get(ScheduleEvent, event_id)
            if event is None:
                raise EventResponseError("NOT_FOUND", "Занятие не найдено.")
            validate_event_available(event, role=user_role(user), squad_id=user.squad_id, now=datetime.now(timezone.utc))
            if response_code == "NOT_COMING":
                reasons = list((await session.scalars(
                    select(AbsenceReason).where(AbsenceReason.is_active.is_(True)).order_by(AbsenceReason.sort_order)
                )).all())
                if callback.message:
                    await callback.message.answer(
                        f"Причина отсутствия на «{event.title}»:",
                        reply_markup=absence_reasons_keyboard(event_id, reasons), parse_mode=None,
                    )
                    if not reasons:
                        await state.set_state(AbsenceReasonStates.awaiting_custom)
                        await state.update_data(event_id=event_id, reason_id=None, user_id=user.id,
                                                started_at=datetime.now(timezone.utc).isoformat())
                        await callback.message.answer("Напишите причину текстом (до 500 символов).", reply_markup=cancel_keyboard())
                await callback.answer()
                return
        await save_event_response(event_id=event_id, user_id=user.id, response_code=response_code)
        if await state.get_state() == AbsenceReasonStates.awaiting_custom.state:
            await state.clear()
    except EventResponseError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    label = {"COMING": "приду", "MAYBE": "уточню позже"}[response_code]
    if callback.message:
        await callback.message.answer(f"Ответ на «{event.title}»: {label}.", reply_markup=event_keyboard(event_id), parse_mode=None)
    await callback.answer("Ответ сохранён.")


@router.callback_query(F.data.startswith("reason:"))
async def absence_reason(callback: CallbackQuery, state: FSMContext) -> None:
    values = callback_ids(callback.data, "reason", 2)
    if values is None:
        await callback.answer("Некорректная причина.", show_alert=True)
        return
    event_id, reason_id = values
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    try:
        async with AsyncSessionLocal() as session:
            event = await session.get(ScheduleEvent, event_id)
            reason = await session.get(AbsenceReason, reason_id)
            if event is None or reason is None or not reason.is_active:
                raise EventResponseError("NOT_FOUND", "Занятие или причина недоступны. Обновите расписание.")
            validate_event_available(event, role=user_role(user), squad_id=user.squad_id, now=datetime.now(timezone.utc))
            if reason.requires_comment:
                await state.set_state(AbsenceReasonStates.awaiting_custom)
                await state.update_data(event_id=event_id, reason_id=reason_id, user_id=user.id,
                                        reason_label=reason.label, started_at=datetime.now(timezone.utc).isoformat())
                if callback.message:
                    await callback.message.answer("Напишите причину одним сообщением (до 500 символов).", reply_markup=cancel_keyboard())
                await callback.answer()
                return
        await save_event_response(event_id=event_id, user_id=user.id, response_code="NOT_COMING", absence_reason_id=reason_id)
        if await state.get_state() == AbsenceReasonStates.awaiting_custom.state:
            await state.clear()
    except EventResponseError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if callback.message:
        await callback.message.answer(f"Ответ записан: не приду. Причина: {reason.label}", reply_markup=event_keyboard(event_id), parse_mode=None)
    await callback.answer("Причина сохранена.")


@router.message(AbsenceReasonStates.awaiting_custom)
async def absence_custom_reason(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    data = await state.get_data()
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Сначала завершите ввод причины или отмените его командой /cancel.", parse_mode=None)
        return
    if not text or len(text) > 500:
        await message.answer("Напишите причину текстом: от 1 до 500 символов.")
        return
    user = await find_user(message.from_user.id)
    if user is None or user.id != data.get("user_id"):
        await state.clear()
        await message.answer("Привязка к составу изменилась. Откройте /schedule заново.")
        return
    try:
        await save_event_response(
            event_id=int(data["event_id"]), user_id=user.id, response_code="NOT_COMING",
            absence_reason_id=data.get("reason_id"), custom_reason=text,
        )
    except EventResponseError as exc:
        await message.answer(str(exc))
        if exc.code not in {"INVALID_REASON", "REASON_REQUIRED"}:
            await state.clear()
        return
    await state.clear()
    await message.answer(f"Ответ записан: не приду. Причина: {text}", reply_markup=main_keyboard(user_role(user)), parse_mode=None)


@router.message(Command("attendance"))
async def attendance(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Посещаемость доступна после подтверждения участия.")
        return
    await send_attendance_text(message, user)


async def send_attendance_text(message: Message, user: User) -> None:
    async with AsyncSessionLocal() as session:
        text = await attendance_text(session, user)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button("personal")]), parse_mode=None)


@router.message(Command("normatives"))
async def normatives(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Нормативы доступны после подтверждения участия.")
        return
    await send_normatives_text(message, user)


async def send_normatives_text(message: Message, user: User, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        text, has_next = await normatives_text(session, user, page)
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"normpage:{page - 1}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"normpage:{page + 1}"))
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=([navigation] if navigation else []) + [home_button()]), parse_mode=None)


@router.callback_query(F.data.startswith("normpage:"))
async def normative_page(callback: CallbackQuery) -> None:
    page = page_number((callback.data or "").partition(":")[2])
    user = await find_user(callback.from_user.id)
    if page is None or callback.message is None or user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Раздел недоступен.", show_alert=True)
        return
    await callback.answer()
    await send_normatives_text(callback.message, user, page)


@router.message(Command("myappeals"))
async def my_appeals_command(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Обращения доступны после подтверждения участия.")
        return
    await send_my_appeals(message, user)


async def send_my_appeals(message: Message, user: User, page: int = 0) -> None:
    page = max(0, min(page, 10000))
    async with AsyncSessionLocal() as session:
        rows = list((await session.scalars(select(Appeal).where(Appeal.author_user_id == user.id).order_by(Appeal.created_at.desc(), Appeal.id.desc()).offset(page * 6).limit(7))).all())
    has_more = len(rows) > 6
    lines = [f"Ваши обращения · страница {page + 1}:"]
    buttons = []
    for item in rows[:6]:
        lines.append(f"#{item.id} · {item.subject[:160]}\n{APPEAL_STATUS_LABELS.get(item.status_code, item.status_code)} · {bot_event_time(item.created_at)}")
        buttons.append([InlineKeyboardButton(text=f"#{item.id} · {item.subject[:40]}", callback_data=f"appealthread:{item.id}:0")])
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"appeallist:{page - 1}"))
    if has_more:
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"appeallist:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    lines.append("\nНовое обращение: /appeal" if rows else "Обращений пока нет. Создать: /appeal")
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[*buttons, [InlineKeyboardButton(text="Новое обращение", callback_data="menu:appeal")], home_button("contact")]), parse_mode=None)


async def send_appeal_thread(message: Message, user: User, appeal_id: int, page: int = 0) -> bool:
    page = max(0, min(page, 10000))
    async with AsyncSessionLocal() as session:
        appeal = await session.get(Appeal, appeal_id)
        if appeal is None or not can_access_appeal(author_id=appeal.author_user_id, user_id=user.id, role=user_role(user)):
            await message.answer("Обращение не найдено или недоступно.", parse_mode=None)
            return False
        # Latest messages first so an incoming answer is immediately visible.
        rows = list((await session.scalars(select(AppealMessage).where(AppealMessage.appeal_id == appeal.id)
                    .order_by(AppealMessage.created_at.desc(), AppealMessage.id.desc()).offset(page * 3).limit(4))).all())
    await message.answer(f"Обращение #{appeal.id}: {appeal.subject}\n{APPEAL_STATUS_LABELS.get(appeal.status_code, appeal.status_code)}", parse_mode=None)
    if page == 0:
        # Older bot appeals have no initial AppealMessage; keep their original text visible too.
        for label, text in (("Описание", appeal.description), ("Решение", appeal.resolution_text)):
            if text:
                for start in range(0, len(text), 1600):
                    await message.answer(f"{label}:\n{text[start:start + 1600]}", parse_mode=None)
    for item in reversed(rows[:3]):
        label = "Вы" if item.author_id == user.id else "Автор" if item.author_id == appeal.author_user_id else "Командование"
        for start in range(0, len(item.body), 1600):
            await message.answer(f"{label} · {bot_event_time(item.created_at)}\n{item.body[start:start + 1600]}", parse_mode=None)
    buttons = [[InlineKeyboardButton(text="Ответить", callback_data=f"appealreply:{appeal.id}")]]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Новее", callback_data=f"appealthread:{appeal.id}:{page - 1}"))
    if len(rows) > 3:
        navigation.append(InlineKeyboardButton(text="Раньше →", callback_data=f"appealthread:{appeal.id}:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    url = app_deep_link(f"/appeals?id={appeal.id}")
    if url:
        buttons.append([InlineKeyboardButton(text="Открыть в приложении", web_app=WebAppInfo(url=url))])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="appeallist:0")])
    await message.answer("Можно ответить здесь или открыть приложение.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode=None)
    return True


@router.message(Command("appealview"))
async def appeal_view_command(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    ids = callback_ids(f"view:{parts[1]}" if len(parts) == 2 else None, "view", 1)
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Обращения доступны после подтверждения участия.", parse_mode=None)
    elif ids is None:
        await message.answer("Используйте /appealview номер, например /appealview 12.", parse_mode=None)
    else:
        await send_appeal_thread(message, user, ids[0])


@router.callback_query(F.data.startswith("appeallist:") | F.data.startswith("appealthread:") | F.data.startswith("appealreply:"))
async def appeal_thread_callback(callback: CallbackQuery, state: FSMContext) -> None:
    user = await find_user(callback.from_user.id)
    if callback.message is None or user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Обращение недоступно.", show_alert=True)
        return
    data = callback.data or ""
    if data.startswith("appeallist:"):
        ids = callback_ids(data, "appeallist", 1)
        # callback_ids intentionally requires positive values; page zero is encoded separately.
        page = 0 if data == "appeallist:0" else ids[0] if ids else None
        if page is None or page > 10000:
            await callback.answer("Кнопка устарела.", show_alert=True)
            return
        await callback.answer()
        await send_my_appeals(callback.message, user, page)
    elif data.startswith("appealthread:"):
        parts = data.split(":")
        ids = callback_ids(":".join(parts[:2]), "appealthread", 1)
        if ids is None or len(parts) != 3 or not re.fullmatch(r"[0-9]{1,5}", parts[2]) or int(parts[2]) > 10000:
            await callback.answer("Кнопка устарела.", show_alert=True)
            return
        await callback.answer()
        await send_appeal_thread(callback.message, user, ids[0], int(parts[2]))
    else:
        ids = callback_ids(data, "appealreply", 1)
        if ids is None:
            await callback.answer("Кнопка устарела.", show_alert=True)
            return
        async with AsyncSessionLocal() as session:
            appeal = await session.get(Appeal, ids[0])
            if appeal is None or not can_access_appeal(author_id=appeal.author_user_id, user_id=user.id, role=user_role(user)):
                await callback.answer("Обращение недоступно.", show_alert=True)
                return
        await state.clear()
        await state.set_state(AppealReplyStates.body)
        await state.update_data(appeal_id=appeal.id, user_id=user.id, started_at=datetime.now(timezone.utc).isoformat())
        await callback.answer()
        await callback.message.answer(f"Напишите ответ на обращение #{appeal.id} одним сообщением (до 4000 символов). Для отмены /cancel.", reply_markup=cancel_keyboard(), parse_mode=None)


@router.message(AppealReplyStates.body)
async def appeal_reply_body(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    if (message.text or "").startswith("/"):
        await message.answer("Команда не отправлена как ответ. Для выхода используйте /cancel.", parse_mode=None)
        return
    try:
        body = validate_appeal_text(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    data = await state.get_data()
    user = await find_user(message.from_user.id)
    async with AsyncSessionLocal() as session:
        appeal = await session.scalar(select(Appeal).where(Appeal.id == data.get("appeal_id")).with_for_update())
        if user is None or user.id != data.get("user_id") or appeal is None or not can_access_appeal(author_id=appeal.author_user_id, user_id=user.id, role=user_role(user)):
            await state.clear()
            await message.answer("Обращение недоступно. Откройте /myappeals заново.", parse_mode=None)
            return
        await add_appeal_reply(session, appeal, sender_id=user.id, role=user_role(user), body=body)
        await session.commit()
    await state.clear()
    await publish_appeal_update()
    await message.answer("Ответ отправлен.", reply_markup=main_keyboard(user_role(user)), parse_mode=None)


@router.message(Command("notifications"))
@router.message(F.text.casefold().in_({"уведомления"}))
async def notifications(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Уведомления доступны после подтверждения участия.")
        return
    await send_notifications_text(message, user)


async def send_notifications_text(message: Message, user: User, page: int = 0, unread_only: bool = False) -> None:
    page = max(0, min(page, 10000))
    mode = int(unread_only)
    async with AsyncSessionLocal() as session:
        counts = await inbox_counts(session, user.id)
        rows = await inbox_page(session, user.id, unread_only=unread_only, limit=INBOX_PAGE_SIZE + 1, offset=page * INBOX_PAGE_SIZE)
    has_next = len(rows) > INBOX_PAGE_SIZE
    rows = rows[:INBOX_PAGE_SIZE]
    lines = [f"Уведомления: {counts['unread']} непрочитанных из {counts['total']}."]
    keyboard_rows = []
    for number, item in enumerate(rows, start=1):
        marker = "●" if not item.is_read else "○"
        lines.append(f"{number}. {marker} {item.title[:180]}")
        keyboard_rows.append([InlineKeyboardButton(text=f"{number}. {item.title[:45]}", callback_data=f"inbox:view:{item.id}:{page}:{mode}")])
    if not rows:
        lines.append("Новых уведомлений нет." if unread_only else "На этой странице уведомлений нет.")
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"inbox:page:{page - 1}:{mode}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"inbox:page:{page + 1}:{mode}"))
    if navigation:
        keyboard_rows.append(navigation)
    keyboard_rows.append([InlineKeyboardButton(text="Все уведомления" if unread_only else "Только непрочитанные", callback_data=f"inbox:page:0:{1 - mode}")])
    if counts["unread"]:
        keyboard_rows.append([InlineKeyboardButton(text="Прочитать все", callback_data="inbox:readall")])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[*keyboard_rows, home_button()]), parse_mode=None)


@router.callback_query(F.data.startswith("inbox:"))
async def inbox_callback(callback: CallbackQuery) -> None:
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT or callback.message is None:
        await callback.answer("Нужна активная привязка к составу.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "page" and len(parts) == 4 and parts[2].isdigit() and parts[3] in {"0", "1"}:
        await callback.answer()
        await send_notifications_text(callback.message, user, int(parts[2]), parts[3] == "1")
        return
    if action == "readall" and len(parts) == 2:
        async with AsyncSessionLocal() as session:
            count = await mark_inbox_read(session, user.id)
            await record_audit(session, user_id=user.id, action_code="notifications.read_all", entity_name="notifications", new_value={"count": count, "source": "BOT"})
            await session.commit()
        await callback.answer(f"Прочитано: {count}")
        await send_notifications_text(callback.message, user)
    elif action == "view" and len(parts) == 5 and all(part.isdigit() for part in parts[2:]) and parts[4] in {"0", "1"}:
        async with AsyncSessionLocal() as session:
            item = await mark_notification_read(session, user.id, int(parts[2]))
            if item is None:
                await callback.answer("Уведомление не найдено.", show_alert=True)
                return
            await session.commit()
            text = f"{item.title[:255]}\n{bot_event_time(item.created_at)}\n\n{(item.body or 'Без дополнительного текста.')[:3000]}"
            buttons = [[InlineKeyboardButton(text="← Назад", callback_data=f"inbox:page:{parts[3]}:{parts[4]}")]]
            url = app_deep_link(item.deep_link)
            if url:
                buttons.insert(0, [InlineKeyboardButton(text="Открыть в приложении", web_app=WebAppInfo(url=url))])
        await callback.answer()
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode=None)
    else:
        await callback.answer("Кнопка устарела. Откройте /notifications заново.", show_alert=True)
        return
    await publish_realtime_event(get_settings(), event_type="notifications.read", user_id=user.id, query_keys=["notifications", "dashboard"])


@router.message(Command("appeal"))
async def appeal_start(message: Message, state: FSMContext) -> None:
    await start_appeal_dialog(message, state, message.from_user.id)


async def start_appeal_dialog(message: Message, state: FSMContext, telegram_id: int) -> None:
    user = await find_user(telegram_id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await message.answer("Обращения доступны после подтверждения участия.", parse_mode=None)
        return
    await state.clear()
    await state.set_state(AppealStates.subject)
    await state.update_data(started_at=datetime.now(timezone.utc).isoformat(), user_id=user.id)
    await message.answer("Напишите тему обращения.", reply_markup=cancel_keyboard(), parse_mode=None)


@router.message(AppealStates.subject)
async def appeal_subject(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    subject = (message.text or "").strip()
    if len(subject) < 3 or len(subject) > 255:
        await message.answer("Тема должна содержать от 3 до 255 символов.", parse_mode=None)
        return
    await state.update_data(subject=subject[:255])
    await state.set_state(AppealStates.description)
    await message.answer("Опишите ситуацию одним сообщением.", reply_markup=cancel_keyboard(), parse_mode=None)


@router.message(AppealStates.description)
async def appeal_description(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    description = (message.text or "").strip()
    if len(description) < 5 or len(description) > 10000:
        await message.answer("Описание должно содержать от 5 до 10000 символов.", parse_mode=None)
        return
    await state.update_data(description=description)
    await state.set_state(AppealStates.urgency)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Обычная", callback_data="appeal_urgency:NORMAL"),
                InlineKeyboardButton(text="Срочная", callback_data="appeal_urgency:HIGH"),
            ],
            [InlineKeyboardButton(text="Очень срочно", callback_data="appeal_urgency:URGENT")],
            [InlineKeyboardButton(text="← Назад", callback_data="dialog:back")],
        ]
    )
    await message.answer("Выберите срочность:", reply_markup=keyboard, parse_mode=None)


@router.message(AppealStates.urgency)
async def appeal_urgency_text(message: Message, state: FSMContext) -> None:
    if await ensure_dialog_not_expired(message, state):
        return
    low = (message.text or "").strip().casefold()
    urgency = {"обычная": "NORMAL", "нормальная": "NORMAL", "срочная": "HIGH", "срочно": "HIGH", "очень срочно": "URGENT"}.get(low)
    if urgency is None:
        await message.answer("Выберите срочность кнопкой или напишите: обычная, срочная, очень срочно.", parse_mode=None)
        return
    await create_appeal_from_state(message, state, urgency)


@router.callback_query(F.data.startswith("appeal_urgency:"))
async def appeal_urgency_callback(callback: CallbackQuery, state: FSMContext) -> None:
    urgency = (callback.data or "").split(":", 1)[1]
    if urgency not in {"LOW", "NORMAL", "HIGH", "URGENT"} or callback.message is None:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    created = await create_appeal_from_state(callback.message, state, urgency, telegram_id=callback.from_user.id)
    await callback.answer("Обращение отправлено." if created else "Откройте /appeal заново.", show_alert=not created)


async def create_appeal_from_state(message: Message, state: FSMContext, urgency: str, *, telegram_id: int | None = None) -> bool:
    if await state.get_state() != AppealStates.urgency.state or await ensure_dialog_not_expired(message, state):
        return False
    data = await state.get_data()
    user_id = int(data.get("user_id") or 0)
    if not data.get("subject") or not data.get("description"):
        await state.clear()
        return False
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or user.telegram_id != (telegram_id if telegram_id is not None else message.from_user.id) or user_role(user) < RoleLevel.PARTICIPANT:
            await state.clear()
            await message.answer("Профиль не найден. Обратитесь к командиру.", parse_mode=None)
            return False
        appeal = Appeal(
            author_user_id=user.id,
            is_anonymous=False,
            subject=str(data.get("subject") or "Обращение")[:255],
            category_code="OTHER",
            description=str(data.get("description") or ""),
            urgency_code=urgency,
            status_code="CREATED",
        )
        session.add(appeal)
        await session.flush()
        session.add(AppealMessage(appeal_id=appeal.id, author_id=user.id, body=appeal.description))
        await record_audit(
            session,
            user_id=user.id,
            action_code="appeal.create_bot",
            entity_name="appeals",
            entity_id=appeal.id,
            new_value={"source": "telegram", "urgency_code": urgency},
        )
        await notify_appeal_commanders(session, appeal, sender_id=user.id, title="Новое обращение",
                                      body=f"{user.full_name}: {appeal.subject}. Срочность: {urgency}.")
        await session.commit()
    await state.clear()
    await publish_appeal_update()
    await message.answer(f"Обращение #{appeal.id} отправлено. Переписка: /appealview {appeal.id}. Ответ придёт в уведомления.", reply_markup=main_keyboard(user_role(user)), parse_mode=None)
    return True


@router.message(Command("applications"))
@router.message(F.text.casefold().in_({"заявки"}))
async def cmd_applications(message: Message) -> None:
    user = await find_user(message.from_user.id)
    if user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await message.answer("Доступ только командирам.")
        return
    await send_applications(message)


async def send_applications(message: Message) -> None:
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
    try:
        submission_id, status_code = int(parts[1]), parts[2]
    except ValueError:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        await callback.answer("Только для командиров.", show_alert=True)
        return
    STATUS_LABELS = {"ACCEPTED": "Принято", "REJECTED": "Отклонено", "NEEDS_REDO": "На доработку"}
    if status_code not in STATUS_LABELS:
        await callback.answer("Некорректный статус.", show_alert=True)
        return
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
        try:
            await callback.message.edit_text(
                f"{status_label} — {norm_title}\nУчастник: {submitter_name}",
                parse_mode=None,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to edit normative review message for submission_id=%s", submission_id)
    await callback.answer(f"Статус: {status_label}")


# ──────────────────────── /schedule batch reply ─────────────────────────────


def batch_events_keyboard(events: list[ScheduleEvent]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Приду на все", callback_data="batch:COMING")],
        [InlineKeyboardButton(text="Ответить по одному", callback_data="batch:ONE_BY_ONE")],
    ])


async def _upcoming_unanswered_events(session, user: User, limit: int = 7) -> list[ScheduleEvent]:
    now = datetime.now(timezone.utc)
    statement = select(ScheduleEvent).outerjoin(
        EventResponse, (EventResponse.event_id == ScheduleEvent.id) & (EventResponse.user_id == user.id),
    ).where(
        ScheduleEvent.start_datetime > now, ScheduleEvent.status_code != "CANCELLED",
        or_(ScheduleEvent.squad_id.is_(None), ScheduleEvent.squad_id == user.squad_id),
        ScheduleEvent.requires_response.is_(True),
        or_(EventResponse.id.is_(None), EventResponse.response_code == "MAYBE"),
    )
    if user_role(user) < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        statement = statement.where(or_(ScheduleEvent.response_deadline_at.is_(None), ScheduleEvent.response_deadline_at >= now))
    return list((await session.scalars(statement.order_by(ScheduleEvent.start_datetime).limit(limit))).all())


@router.callback_query(F.data.startswith("batch:"))
async def batch_response(callback: CallbackQuery) -> None:
    action = (callback.data or "").partition(":")[2]
    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        await callback.answer("Нужна привязка к составу.", show_alert=True)
        return
    if action not in {"COMING", "NOT_COMING", "ONE_BY_ONE"}:
        await callback.answer("Некорректный ответ.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        events = await _upcoming_unanswered_events(session, user)
    if not events:
        await callback.answer("Нет занятий, ожидающих ответа.", show_alert=True)
        return
    # Old 'NOT_COMING' buttons also collect a reason for each event.
    if action != "COMING":
        await callback.answer()
        if callback.message:
            for event in events:
                await callback.message.answer(f"{event.title}\n{bot_event_time(event.start_datetime)}", reply_markup=event_keyboard(event.id), parse_mode=None)
        return
    try:
        async with AsyncSessionLocal() as session:
            locked = list((await session.scalars(select(ScheduleEvent).where(ScheduleEvent.id.in_([event.id for event in events])).order_by(ScheduleEvent.id).with_for_update())).all())
            if len(locked) != len(events):
                raise EventResponseError("NOT_FOUND", "Одно из занятий удалено. Обновите /schedule.")
            responses = dict((await session.execute(select(EventResponse.event_id, EventResponse.response_code).where(
                EventResponse.user_id == user.id, EventResponse.event_id.in_([event.id for event in locked]),
            ))).all())
            locked = [event for event in locked if responses.get(event.id) in {None, "MAYBE"}]
            if not locked:
                raise EventResponseError("ALREADY_ANSWERED", "Все ответы уже сохранены. Изменить их можно через /schedule.")
            now = datetime.now(timezone.utc)
            for event in locked:
                validate_event_available(event, role=user_role(user), squad_id=user.squad_id, now=now)
            for event in locked:
                await respond_to_event(session, event=event, user_id=user.id, role=user_role(user), squad_id=user.squad_id, response_code="COMING", source_code="BOT", now=now)
            await record_audit(session, user_id=user.id, action_code="schedule_event.respond_bulk", entity_name="schedule_events", new_value={"event_ids": [event.id for event in locked], "source": "BOT"})
            await session.commit()
    except EventResponseError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Ответы сохранены.")
    if callback.message:
        await callback.message.answer(f"Ответ «Приду» сохранён для {len(locked)} занятий. Изменить: /schedule", parse_mode=None)
    await publish_realtime_event(get_settings(), event_type="schedule.response.updated", user_id=user.id, query_keys=["schedule", "dashboard"])


# ──────────────────────── commander attendance via bot ─────────────────────


def attendance_mark_keyboard(
    *,
    event_id: int,
    users: list[User],
    existing_status: dict[int, str],
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        name = user.full_name.split()[0] if user.full_name else f"#{user.id}"
        status_code = existing_status.get(user.id)
        present_label = f"{name}: был" if status_code != "PRESENT" else f"{name}: был ✓"
        late_label = "опоздал" if status_code != "LATE" else "опоздал ✓"
        absent_label = "нет" if status_code != "ABSENT" else "нет ✓"
        rows.append(
            [
                InlineKeyboardButton(text=present_label[:32], callback_data=f"attmark:{event_id}:{user.id}:PRESENT:{page}"),
                InlineKeyboardButton(text=late_label, callback_data=f"attmark:{event_id}:{user.id}:LATE:{page}"),
                InlineKeyboardButton(text=absent_label, callback_data=f"attmark:{event_id}:{user.id}:ABSENT:{page}"),
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="Назад", callback_data=f"attpage:{event_id}:{page - 1}"))
    if (page + 1) * ATTENDANCE_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="Дальше", callback_data=f"attpage:{event_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(home_button("command"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _attendance_event_context(session, commander: User, event_id: int) -> tuple[ScheduleEvent | None, str | None]:
    event = await session.get(ScheduleEvent, event_id)
    if event is None:
        return None, "Событие не найдено."
    role = user_role(commander)
    if role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        return None, "Отмечать явку могут только командиры."
    if role < RoleLevel.DEPUTY_PLATOON_COMMANDER and commander.squad_id is None:
        return None, "У вас не назначено отделение."
    if role < RoleLevel.DEPUTY_PLATOON_COMMANDER and event.squad_id is not None and event.squad_id != commander.squad_id:
        return None, "Это событие другого отделения."
    return event, None


async def send_attendance_mark_page(message: Message, commander: User, event_id: int, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        event, error = await _attendance_event_context(session, commander, event_id)
        if error or event is None:
            await message.answer(error or "Событие недоступно.")
            return
        statement = select(User).where(User.status_code == "ACTIVE", User.role_code.in_(PARTICIPANT_ROLE_CODES))
        if event.squad_id is not None:
            statement = statement.where(User.squad_id == event.squad_id)
        elif user_role(commander) < RoleLevel.DEPUTY_PLATOON_COMMANDER and commander.squad_id is not None:
            statement = statement.where(User.squad_id == commander.squad_id)
        participants = list((await session.scalars(statement.order_by(User.full_name))).all())
        total = len(participants)
        page = max(0, page)
        page_users = participants[page * ATTENDANCE_PAGE_SIZE:(page + 1) * ATTENDANCE_PAGE_SIZE]
        if not page_users:
            await message.answer("Некого отмечать по этому событию.")
            return
        rows = (
            await session.execute(
                select(Attendance.user_id, Attendance.status_code).where(
                    Attendance.event_id == event.id,
                    Attendance.user_id.in_([user.id for user in page_users]),
                )
            )
        ).all()
    status_by_user = {user_id: status_code for user_id, status_code in rows}
    text = (
        f"Явка: {event.title}\n"
        f"Страница {page + 1}/{max(1, (total + ATTENDANCE_PAGE_SIZE - 1) // ATTENDANCE_PAGE_SIZE)}"
    )
    await message.answer(
        text,
        reply_markup=attendance_mark_keyboard(
            event_id=event_id,
            users=page_users,
            existing_status=status_by_user,
            page=page,
            total=total,
        ),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("attendance:"))
async def attendance_open_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    try:
        event_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (IndexError, ValueError):
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    commander = await find_user(callback.from_user.id)
    if commander is None:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    if callback.message:
        await send_attendance_mark_page(callback.message, commander, event_id, page)
    await callback.answer()


@router.callback_query(F.data.startswith("attpage:"))
async def attendance_page_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    try:
        event_id = int(parts[1])
        page = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    commander = await find_user(callback.from_user.id)
    if commander is None:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    if callback.message:
        await callback.message.delete()
        await send_attendance_mark_page(callback.message, commander, event_id, page)
    await callback.answer()


@router.callback_query(F.data.startswith("attmark:"))
async def attendance_mark_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    try:
        event_id = int(parts[1])
        participant_id = int(parts[2])
        status_code = parts[3]
        page = int(parts[4])
    except (IndexError, ValueError):
        await callback.answer("Некорректная отметка.", show_alert=True)
        return
    if status_code not in {"PRESENT", "LATE", "ABSENT"}:
        await callback.answer("Некорректный статус.", show_alert=True)
        return
    commander = await find_user(callback.from_user.id)
    if commander is None:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        db_commander = await session.get(User, commander.id)
        if db_commander is None:
            await callback.answer("Профиль не найден.", show_alert=True)
            return
        event, error = await _attendance_event_context(session, db_commander, event_id)
        participant = await session.get(User, participant_id)
        if error or event is None or participant is None:
            await callback.answer(error or "Участник не найден.", show_alert=True)
            return
        if event.squad_id is not None and participant.squad_id != event.squad_id:
            await callback.answer("Участник из другого отделения.", show_alert=True)
            return
        attendance_row = await session.scalar(
            select(Attendance).where(Attendance.event_id == event_id, Attendance.user_id == participant_id)
        )
        old_status = attendance_row.status_code if attendance_row else None
        if attendance_row is None:
            attendance_row = Attendance(event_id=event_id, user_id=participant_id)
            session.add(attendance_row)
        attendance_row.status_code = status_code
        attendance_row.marked_by_user_id = db_commander.id
        attendance_row.marked_at = now
        attendance_row.source_code = "BOT"
        attendance_row.updated_at = now
        await session.flush()
        await record_audit(
            session,
            user_id=db_commander.id,
            action_code="attendance.mark_bot",
            entity_name="attendance",
            entity_id=attendance_row.id,
            old_value={"status_code": old_status},
            new_value={"event_id": event_id, "user_id": participant_id, "status_code": status_code},
        )
        await session.commit()
    if callback.message:
        await callback.message.delete()
        await send_attendance_mark_page(callback.message, commander, event_id, page)
    await callback.answer("Явка обновлена.")


# ──────────────────────── /schedule — enriched with batch ───────────────────


async def _send_schedule_with_batch(message: Message, user: User, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        event, text, actionable, has_next = await schedule_card(session, user, page)
    rows = event_keyboard(event.id).inline_keyboard[:-1] if event and actionable else []
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Раньше", callback_data=f"schedulepage:{page - 1}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="Дальше →", callback_data=f"schedulepage:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append(home_button())
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode=None)


@router.callback_query(F.data.startswith("schedulepage:"))
async def schedule_page_callback(callback: CallbackQuery) -> None:
    page = page_number((callback.data or "").partition(":")[2])
    user = await find_user(callback.from_user.id)
    if page is None or user is None or user_role(user) < RoleLevel.PARTICIPANT or callback.message is None:
        await callback.answer("Расписание недоступно.", show_alert=True)
        return
    await callback.answer()
    await _send_schedule_with_batch(callback.message, user, page)


# ──────────────────────── video/photo/doc → normative ───────────────────────


class NormativeFileStates(StatesGroup):
    awaiting_normative_choice = State()


def normative_choice_keyboard(normatives: list[Normative], page: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=n.title[:40], callback_data=f"norm_submit:{n.id}")]
        for n in normatives[:5]
    ]
    nav = []
    if page:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"normchoicepage:{page - 1}"))
    if len(normatives) > 5:
        nav.append(InlineKeyboardButton(text="Далее →", callback_data=f"normchoicepage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="dialog:back"), InlineKeyboardButton(text="Отмена", callback_data="norm_submit:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.video | F.photo | F.document)
async def handle_file_message(message: Message, state: FSMContext) -> None:
    user = await find_user(message.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT:
        return  # silently ignore from non-participants
    async with AsyncSessionLocal() as session:
        normatives = await normative_choices(session, user)
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
    await state.update_data(file_id=file_id, user_id=user.id, started_at=datetime.now(timezone.utc).isoformat())
    await message.answer(
        "Это файл для сдачи норматива?\nВыберите норматив или отмените:",
        reply_markup=normative_choice_keyboard(normatives),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("normchoicepage:"))
async def normative_choice_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = page_number((callback.data or "").partition(":")[2])
    data = await state.get_data()
    user = await find_user(callback.from_user.id)
    if page is None or user is None or user_role(user) < RoleLevel.PARTICIPANT or data.get("user_id") != user.id or not data.get("file_id") or await state.get_state() != NormativeFileStates.awaiting_normative_choice.state or callback.message is None:
        await callback.answer("Пришлите файл заново.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        rows = await normative_choices(session, user, page)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=normative_choice_keyboard(rows, page))


@router.callback_query(F.data.startswith("norm_submit:"))
async def normative_file_submit(callback: CallbackQuery, state: FSMContext) -> None:
    norm_id_str = (callback.data or "").split(":")[1]
    if norm_id_str == "cancel":
        await state.clear()
        await callback.message.edit_text("Понял, файл не для норматива.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[home_button()]))
        await callback.answer()
        return
    norm_id = entity_id(norm_id_str)
    if norm_id is None:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    if callback.message is None or await ensure_dialog_not_expired(callback.message, state):
        await callback.answer("Пришлите файл заново.", show_alert=True)
        return
    data = await state.get_data()
    file_id: str = data.get("file_id", "")
    stored_user_id: int = data.get("user_id", 0)

    user = await find_user(callback.from_user.id)
    if user is None or user_role(user) < RoleLevel.PARTICIPANT or user.id != stored_user_id or not file_id or await state.get_state() != NormativeFileStates.awaiting_normative_choice.state:
        await callback.answer("Ошибка сессии.", show_alert=True)
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        normative = await session.get(Normative, norm_id)
        if not normative or not normative.is_active or (normative.squad_id is not None and normative.squad_id != user.squad_id):
            await callback.answer("Норматив недоступен.", show_alert=True)
            return
        submission = await submit_normative_service(
            session,
            normative=normative,
            submitter=user,
            status_code="PENDING",
            comment=f"[TG file_id: {file_id}]",
            file_ids=None,
            audit_action_code="normative_submission.submit_via_bot",
            audit_value={"normative_id": norm_id, "telegram_file_id": file_id, "source": "bot"},
            notification_body=f"{user.full_name} прислал файл на проверку по нормативу «{normative.title}».",
            notification_scope="submitter_squad",
        )
        await session.commit()
        await session.refresh(submission)
        normative_title = normative.title
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            f"Файл принят на проверку по нормативу «{normative_title}».\nКомандир получил уведомление.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← К нормативам", callback_data="menu:normatives")]]),
            parse_mode=None,
        )
    await callback.answer("Сдача отправлена!")


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


@router.errors()
async def bot_error_handler(event: ErrorEvent) -> bool:
    logger.exception("Unhandled Telegram bot error", exc_info=event.exception)
    update = event.update
    message = getattr(update, "message", None) or getattr(update, "callback_query", None)
    try:
        if getattr(message, "message", None):
            await message.message.answer("Произошла ошибка. Попробуйте позже.", parse_mode=None)
        elif hasattr(message, "answer"):
            await message.answer("Произошла ошибка. Попробуйте позже.", parse_mode=None)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to notify user about bot error")
    return True


def build_storage(settings):
    if settings.redis_url:
        return RedisStorage.from_url(
            settings.redis_url,
            state_ttl=int(JOIN_STATE_TIMEOUT.total_seconds()),
            data_ttl=int(JOIN_STATE_TIMEOUT.total_seconds()),
        )
    return MemoryStorage()


async def main() -> None:
    configure_json_logging()
    settings = get_settings()
    init_sentry(settings, service_name="telegram_bot")
    asyncio.create_task(heartbeat_loop(settings.bot_heartbeat_path))
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
        BotCommand(command="schedule", description="Ближайшее занятие и ответ"),
        BotCommand(command="checkin", description="Отметить присутствие"),
        BotCommand(command="notifications", description="Уведомления"),
        BotCommand(command="cancel", description="Отменить ввод и вернуться"),
        BotCommand(command="help", description="Все возможности и команды"),
    ])
    storage = build_storage(settings)
    isolation = storage.create_isolation() if isinstance(storage, RedisStorage) else SimpleEventIsolation()
    dispatcher = Dispatcher(storage=storage, events_isolation=isolation)
    dispatcher.include_router(router)
    logger.info("Starting VPK Zvezda Telegram bot")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
