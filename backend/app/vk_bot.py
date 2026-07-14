from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update

from .config import get_settings
from .database import AsyncSessionLocal
from .models import AbsenceReason, Appeal, EventResponse, Notification, Normative, ScheduleEvent, User
from .roles import RoleLevel, role_level
from .services.auth_security import (
    PasswordPolicyError,
    bump_token_version,
    password_lockout_state,
    register_failed_password_login,
    register_successful_password_login,
    validate_password_policy,
)
from .services.attendance import SelfCheckInError, self_check_in, sync_automatic_grade
from .services.events import save_event_response as save_event_response_service
from .services.heartbeat import start_heartbeat_thread
from .services.normatives import submit_normative as submit_normative_service
from .services.observability import configure_json_logging, init_sentry
from .services.sessions import consume_fixed_window_limit, delete_user_sessions
from .utils.audit import record_audit
from .utils.channel_link import redeem_link_code
from .utils.password import hash_password, verify_password

logger = logging.getLogger(__name__)

# Redis-backed dialog state in production; the in-memory fallback is for local development only.
_vk_login_state: dict[int, dict] = {}
_vk_event_state: dict[int, dict] = {}
_redis_client: Redis | None = None
_LOGIN_STATE_TTL_SECONDS = 600


def _state_key(kind: str, vk_id: int) -> str:
    return f"botvpk:vk:{kind}:{vk_id}"


def _get_redis() -> Redis | None:
    global _redis_client
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def _get_state(kind: str, vk_id: int) -> dict | None:
    redis = _get_redis()
    if redis is not None:
        raw = await redis.get(_state_key(kind, vk_id))
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            await redis.delete(_state_key(kind, vk_id))
            return None
        return value if isinstance(value, dict) else None

    storage = _vk_login_state if kind == "login" else _vk_event_state
    state = storage.get(vk_id)
    if not state:
        return None
    age = (datetime.now(timezone.utc) - state["ts"]).total_seconds()
    if age > _LOGIN_STATE_TTL_SECONDS:
        storage.pop(vk_id, None)
        return None
    return state


async def _set_state(kind: str, vk_id: int, **data) -> None:
    redis = _get_redis()
    if redis is not None:
        await redis.setex(
            _state_key(kind, vk_id),
            _LOGIN_STATE_TTL_SECONDS,
            json.dumps(data, ensure_ascii=False, default=str),
        )
        return
    storage = _vk_login_state if kind == "login" else _vk_event_state
    storage[vk_id] = {**data, "ts": datetime.now(timezone.utc)}


async def _clear_state(kind: str, vk_id: int) -> None:
    redis = _get_redis()
    if redis is not None:
        await redis.delete(_state_key(kind, vk_id))
        return
    storage = _vk_login_state if kind == "login" else _vk_event_state
    storage.pop(vk_id, None)


async def _get_login_state(vk_id: int) -> dict | None:
    return await _get_state("login", vk_id)


async def _set_login_state(vk_id: int, **data) -> None:
    await _set_state("login", vk_id, **data)


async def _clear_login_state(vk_id: int) -> None:
    await _clear_state("login", vk_id)


async def _get_event_state(vk_id: int) -> dict | None:
    return await _get_state("event", vk_id)


async def _set_event_state(vk_id: int, **data) -> None:
    await _set_state("event", vk_id, **data)


async def _clear_event_state(vk_id: int) -> None:
    await _clear_state("event", vk_id)

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

_CODE_RE = re.compile(r"^\s*(\d{6})\s*$")
_RESPONSE_LABELS = {
    "COMING": "Приду",
    "NOT_COMING": "Не приду",
    "MAYBE": "Уточню",
}


def _text_button(label: str, color: str = "secondary", payload: dict | None = None) -> dict:
    action = {"type": "text", "label": label}
    if payload is not None:
        action["payload"] = json.dumps(payload, ensure_ascii=False)
    return {"action": action, "color": color}


def main_keyboard(site_url: str | None = None) -> str:
    buttons = [
        [_text_button("Расписание", "primary")],
        [_text_button("Отметиться", "positive")],
        [_text_button("Уведомления")],
        [_text_button("Профиль")],
        [_text_button("Обращение")],
        [_text_button("Сбросить пароль")],
        [_text_button("Отвязать")],
    ]
    if site_url:
        buttons.append([_text_button("Открыть сайт", "primary")])
    return json.dumps({"one_time": False, "buttons": buttons}, ensure_ascii=False)


def with_site_link(text: str, site_url: str | None) -> str:
    if not site_url:
        return text
    return f"{text}\n\nСайт: {site_url}"


def empty_keyboard() -> str:
    return json.dumps({"buttons": [], "one_time": True}, ensure_ascii=False)


def login_entry_keyboard() -> str:
    return json.dumps(
        {
            "one_time": False,
            "buttons": [
                [_text_button("Войти по паролю", "primary")],
                [_text_button("Войти по коду")],
            ],
        },
        ensure_ascii=False,
    )


async def find_user_by_vk(vk_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(User).where(User.vk_id == vk_id))


async def _self_checkin_from_vk(message, user: User, site_url: str | None) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.self_checkin_enabled.is_(True),
                        ScheduleEvent.status_code != "CANCELLED",
                        (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == user.squad_id),
                        ScheduleEvent.start_datetime >= now.replace(microsecond=0) - timedelta(hours=2),
                        ScheduleEvent.start_datetime <= now.replace(microsecond=0) + timedelta(hours=2),
                    )
                    .order_by(ScheduleEvent.start_datetime)
                )
            ).all()
        )
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
                    action_code="attendance.self_checkin_vk",
                    entity_name="attendance",
                    entity_id=attendance_row.id,
                    new_value={"event_id": event.id, "status_code": attendance_row.status_code, "source_code": "BOT"},
                )
            await session.commit()
            label = "опоздание" if attendance_row.status_code == "LATE" else "присутствие"
            await message.answer(f"{event.title}: {label} отмечено.", keyboard=main_keyboard(site_url))
            return
    await message.answer(
        str(last_error) if last_error else "Сейчас нет события с открытым окном самоотметки.",
        keyboard=main_keyboard(site_url),
    )


async def _handle_password_reset_state(message, user: User, state: dict, text: str, site_url: str | None) -> bool:
    step = state.get("step")
    if step == "reset_password_new":
        try:
            validate_password_policy(text, telegram_id=user.telegram_id)
        except PasswordPolicyError as exc:
            await message.answer(f"Пароль не подходит: {exc}\nВведите другой пароль или напишите «Отмена».")
            return True
        await _set_event_state(message.from_id, step="reset_password_confirm", password=text)
        await message.answer("Повторите новый пароль.")
        return True
    if step == "reset_password_confirm":
        if text != state.get("password"):
            await _set_event_state(message.from_id, step="reset_password_new")
            await message.answer("Пароли не совпали. Введите новый пароль заново.")
            return True
        settings = get_settings()
        if not await consume_fixed_window_limit(
            settings,
            f"vk-password-reset:{message.from_id}",
            limit=5,
            window_seconds=600,
        ):
            await _clear_event_state(message.from_id)
            await message.answer("Слишком много попыток. Повторите через 10 минут.", keyboard=main_keyboard(site_url))
            return True
        async with AsyncSessionLocal() as session:
            db_user = await session.get(User, user.id)
            if db_user is None:
                await _clear_event_state(message.from_id)
                return True
            db_user.password_hash = hash_password(text)
            db_user.password_set_at = datetime.now(timezone.utc)
            db_user.updated_at = datetime.now(timezone.utc)
            bump_token_version(db_user)
            await record_audit(
                session,
                user_id=db_user.id,
                action_code="auth.password.reset_vk",
                entity_name="users",
                entity_id=db_user.id,
            )
            await session.commit()
        await delete_user_sessions(settings, user.id)
        await _clear_event_state(message.from_id)
        await message.answer("Пароль сайта обновлён.", keyboard=main_keyboard(site_url))
        return True
    return False


def schedule_response_keyboard(events: list[tuple[int, ScheduleEvent]], site_url: str | None) -> str:
    buttons = []
    for number, event in events:
        base_payload = {"action": "event_response", "event_id": event.id}
        buttons.append(
            [
                _text_button(
                    f"{number} Приду",
                    "positive",
                    {**base_payload, "response_code": "COMING"},
                ),
                _text_button(
                    f"{number} Уточню",
                    "secondary",
                    {**base_payload, "response_code": "MAYBE"},
                ),
            ]
        )
        buttons.append(
            [
                _text_button(
                    f"{number} Не приду",
                    "negative",
                    {**base_payload, "response_code": "NOT_COMING"},
                )
            ]
        )
    navigation = [_text_button("Меню")]
    if site_url:
        navigation.append(_text_button("Открыть сайт", "primary"))
    buttons.append(navigation)
    return json.dumps({"one_time": False, "buttons": buttons}, ensure_ascii=False)


def absence_reasons_keyboard(event_id: int, reasons: list[AbsenceReason]) -> str:
    buttons = [
        [
            _text_button(
                reason.label[:40],
                "secondary",
                {
                    "action": "absence_reason",
                    "event_id": event_id,
                    "reason_id": reason.id,
                },
            )
        ]
        for reason in reasons[:8]
    ]
    buttons.append([_text_button("Отмена", "negative")])
    return json.dumps({"one_time": False, "buttons": buttons}, ensure_ascii=False)


def appeal_urgency_keyboard() -> str:
    return json.dumps(
        {
            "one_time": False,
            "buttons": [
                [
                    _text_button("Обычная", "secondary", {"action": "appeal_urgency", "urgency": "NORMAL"}),
                    _text_button("Срочная", "negative", {"action": "appeal_urgency", "urgency": "HIGH"}),
                ],
                [_text_button("Очень срочно", "negative", {"action": "appeal_urgency", "urgency": "URGENT"})],
                [_text_button("Отмена", "negative")],
            ],
        },
        ensure_ascii=False,
    )


def normative_choice_keyboard(normatives: list[Normative]) -> str:
    buttons = [
        [
            _text_button(
                normative.title[:40],
                "secondary",
                {"action": "norm_submit", "normative_id": normative.id},
            )
        ]
        for normative in normatives[:8]
    ]
    buttons.append([_text_button("Отмена", "negative")])
    return json.dumps({"one_time": False, "buttons": buttons}, ensure_ascii=False)


def _message_payload(raw_payload) -> dict:
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            value = json.loads(raw_payload)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _serialize_attachments(message) -> str:
    attachments = getattr(message, "attachments", None) or []
    if not attachments:
        return ""
    values: list[str] = []
    for attachment in attachments:
        attachment_type = getattr(attachment, "type", None)
        if isinstance(attachment, dict):
            attachment_type = attachment.get("type", attachment_type)
        values.append(f"{attachment_type or 'attachment'}: {attachment}")
    return "\n".join(values)[:3000]


async def _schedule_overview(user: User) -> tuple[str, list[tuple[int, ScheduleEvent]]]:
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
                    )
                    .order_by(ScheduleEvent.start_datetime)
                    .limit(4)
                )
            ).all()
        )
        response_rows = []
        if events:
            response_rows = (
                await session.execute(
                    select(EventResponse.event_id, EventResponse.response_code).where(
                        EventResponse.user_id == user.id,
                        EventResponse.event_id.in_([event.id for event in events]),
                    )
                )
            ).all()
    if not events:
        return "Ближайших событий пока нет.", []
    response_by_event = {event_id: response_code for event_id, response_code in response_rows}
    lines = ["Ближайшие занятия:"]
    actionable: list[tuple[int, ScheduleEvent]] = []
    for number, event in enumerate(events, start=1):
        start_at = event.start_datetime.strftime("%d.%m %H:%M")
        place = f" · {event.place}" if event.place else ""
        response_code = response_by_event.get(event.id)
        if response_code:
            response_label = _RESPONSE_LABELS.get(response_code, response_code)
        elif not event.requires_response:
            response_label = "Ответ не требуется"
        elif event.response_deadline_at and now > event.response_deadline_at:
            response_label = "Ответ закрыт"
        else:
            response_label = "Нет ответа"
        lines.append(f"\n{number}. {event.title}\n{start_at}{place}\nОтвет: {response_label}")
        if event.requires_response and not (event.response_deadline_at and now > event.response_deadline_at):
            actionable.append((number, event))
    if actionable:
        lines.append("\nВыберите ответ кнопками ниже.")
    return "\n".join(lines), actionable


async def _send_schedule(message, user: User, site_url: str | None, prefix: str | None = None) -> None:
    text, actionable = await _schedule_overview(user)
    if prefix:
        text = f"{prefix}\n\n{text}"
    keyboard = schedule_response_keyboard(actionable, site_url) if actionable else main_keyboard(site_url)
    await message.answer(text, keyboard=keyboard)


async def _event_for_response(session, user: User, event_id: int) -> tuple[ScheduleEvent | None, str | None]:
    event = await session.get(ScheduleEvent, event_id)
    if event is None:
        return None, "Занятие не найдено. Обновите расписание."
    if event.status_code == "CANCELLED":
        return None, "Занятие отменено."
    if event.start_datetime < datetime.now(timezone.utc):
        return None, "Занятие уже началось, ответ закрыт."
    if event.squad_id is not None and event.squad_id != user.squad_id and role_level(user.role_code) < RoleLevel.SQUAD_COMMANDER:
        return None, "Это занятие недоступно вашему отделению."
    if not event.requires_response:
        return None, "Для этого занятия ответ не требуется."
    if event.response_deadline_at and datetime.now(timezone.utc) > event.response_deadline_at:
        return None, "Срок ответа на это занятие уже прошёл."
    return event, None


async def _save_event_response(
    session,
    *,
    event: ScheduleEvent,
    user: User,
    response_code: str,
    absence_reason_id: int | None = None,
    custom_reason: str | None = None,
) -> None:
    existing = await session.scalar(
        select(EventResponse).where(EventResponse.event_id == event.id, EventResponse.user_id == user.id)
    )
    old_value = (
        {
            "response_code": existing.response_code,
            "absence_reason_id": existing.absence_reason_id,
            "custom_reason": existing.custom_reason,
        }
        if existing is not None
        else None
    )
    await save_event_response_service(
        session,
        event_id=event.id,
        user_id=user.id,
        response_code=response_code,
        absence_reason_id=absence_reason_id,
        custom_reason=custom_reason,
        source_code="VK",
    )
    await record_audit(
        session,
        user_id=user.id,
        action_code="schedule_event.respond",
        entity_name="schedule_events",
        entity_id=event.id,
        old_value=old_value,
        new_value={
            "response_code": response_code,
            "absence_reason_id": absence_reason_id,
            "custom_reason": custom_reason,
            "source_code": "VK",
        },
    )


async def _handle_event_response(message, user: User, payload: dict, site_url: str | None) -> None:
    try:
        event_id = int(payload["event_id"])
    except (KeyError, TypeError, ValueError):
        await message.answer("Не удалось определить занятие. Обновите расписание.")
        return
    response_code = str(payload.get("response_code", ""))
    if response_code not in _RESPONSE_LABELS:
        await message.answer("Некорректный вариант ответа. Обновите расписание.")
        return

    async with AsyncSessionLocal() as session:
        event, error = await _event_for_response(session, user, event_id)
        if error or event is None:
            await message.answer(error or "Занятие недоступно.")
            return
        if response_code == "NOT_COMING":
            reasons = list(
                (
                    await session.scalars(
                        select(AbsenceReason)
                        .where(AbsenceReason.is_active.is_(True))
                        .order_by(AbsenceReason.sort_order)
                    )
                ).all()
            )
            if reasons:
                await message.answer(
                    f"Почему вы не придёте на «{event.title}»?",
                    keyboard=absence_reasons_keyboard(event.id, reasons),
                )
            else:
                await _set_event_state(
                    message.from_id,
                    step="awaiting_absence_comment",
                    event_id=event.id,
                    reason_id=None,
                    reason_label="Своя причина",
                )
                await message.answer("Напишите причину отсутствия одним сообщением или нажмите «Отмена».")
            return
        await _save_event_response(session, event=event, user=user, response_code=response_code)
        await session.commit()

    await _send_schedule(
        message,
        user,
        site_url,
        prefix=f"Ответ сохранён: {_RESPONSE_LABELS[response_code].lower()}.",
    )


async def _handle_absence_reason(message, user: User, payload: dict, site_url: str | None) -> None:
    try:
        event_id = int(payload["event_id"])
        reason_id = int(payload["reason_id"])
    except (KeyError, TypeError, ValueError):
        await message.answer("Не удалось определить причину. Выберите ответ заново.")
        return

    async with AsyncSessionLocal() as session:
        event, error = await _event_for_response(session, user, event_id)
        if error or event is None:
            await message.answer(error or "Занятие недоступно.")
            return
        reason = await session.get(AbsenceReason, reason_id)
        if reason is None or not reason.is_active:
            await message.answer("Эта причина больше недоступна. Выберите ответ заново.")
            return
        if reason.requires_comment:
            await _set_event_state(
                message.from_id,
                step="awaiting_absence_comment",
                event_id=event.id,
                reason_id=reason.id,
                reason_label=reason.label,
            )
            await message.answer(
                f"Уточните причину «{reason.label}» одним сообщением или нажмите «Отмена»."
            )
            return
        await _save_event_response(
            session,
            event=event,
            user=user,
            response_code="NOT_COMING",
            absence_reason_id=reason.id,
        )
        await session.commit()

    await _send_schedule(
        message,
        user,
        site_url,
        prefix=f"Ответ сохранён: не приду. Причина: {reason.label}.",
    )


async def _save_absence_comment(message, user: User, state: dict, comment: str, site_url: str | None) -> None:
    async with AsyncSessionLocal() as session:
        event, error = await _event_for_response(session, user, int(state["event_id"]))
        if error or event is None:
            await _clear_event_state(message.from_id)
            await message.answer(error or "Занятие недоступно.")
            return
        reason_id = state.get("reason_id")
        if reason_id is not None:
            reason = await session.get(AbsenceReason, int(reason_id))
            if reason is None or not reason.is_active:
                await _clear_event_state(message.from_id)
                await message.answer("Эта причина больше недоступна. Выберите ответ заново.")
                return
        await _save_event_response(
            session,
            event=event,
            user=user,
            response_code="NOT_COMING",
            absence_reason_id=int(reason_id) if reason_id is not None else None,
            custom_reason=comment,
        )
        await session.commit()
    await _clear_event_state(message.from_id)
    await _send_schedule(
        message,
        user,
        site_url,
        prefix=f"Ответ сохранён: не приду. Причина: {state.get('reason_label')}: {comment}.",
    )


async def _notifications_text(user: User) -> str:
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
        return "Уведомлений пока нет."
    unread = sum(1 for r in rows if not r.is_read)
    lines = [f"🔔 Уведомления ({unread} новых):"]
    for item in rows:
        prefix = "🔵" if not item.is_read else "•"
        lines.append(f"{prefix} {item.title}")
    return "\n".join(lines)


def _profile_text(user: User) -> str:
    return "\n".join(
        [
            "👤 Профиль",
            user.full_name,
            f"Должность: {ROLE_LABELS.get(user.role_code, user.role_code)}",
            f"Отделение: {user.squad_id or 'не назначено'}",
        ]
    )


async def _start_appeal(message, user: User) -> None:
    await _set_event_state(message.from_id, step="appeal_subject")
    await message.answer("Напишите тему обращения одним сообщением.", keyboard=empty_keyboard())


async def _handle_appeal_state(message, user: User, state: dict, text: str, site_url: str | None) -> bool:
    step = state.get("step")
    if step == "appeal_subject":
        subject = text.strip()
        if len(subject) < 3:
            await message.answer("Тема слишком короткая. Напишите чуть подробнее.")
            return True
        await _set_event_state(message.from_id, step="appeal_description", subject=subject)
        await message.answer("Теперь опишите ситуацию. Это сообщение уйдёт командирам.")
        return True

    if step == "appeal_description":
        description = text.strip()
        if len(description) < 5:
            await message.answer("Описание слишком короткое. Добавьте деталей.")
            return True
        await _set_event_state(
            message.from_id,
            step="appeal_urgency",
            subject=state.get("subject", "Обращение"),
            description=description,
        )
        await message.answer("Выберите срочность.", keyboard=appeal_urgency_keyboard())
        return True

    if step == "appeal_urgency":
        urgency = "HIGH" if "сроч" in text.casefold() else "NORMAL"
        await _create_appeal_from_vk(message, user, state, urgency, site_url)
        return True

    return False


async def _handle_appeal_urgency_payload(message, user: User, payload: dict, site_url: str | None) -> None:
    state = await _get_event_state(message.from_id)
    if not state or state.get("step") != "appeal_urgency":
        await message.answer("Начните обращение кнопкой «Обращение».", keyboard=main_keyboard(site_url))
        return
    urgency = str(payload.get("urgency") or "NORMAL")
    if urgency not in {"LOW", "NORMAL", "HIGH", "URGENT"}:
        urgency = "NORMAL"
    await _create_appeal_from_vk(message, user, state, urgency, site_url)


async def _create_appeal_from_vk(message, user: User, state: dict, urgency: str, site_url: str | None) -> None:
    async with AsyncSessionLocal() as session:
        appeal = Appeal(
            author_user_id=user.id,
            is_anonymous=False,
            subject=str(state.get("subject") or "Обращение")[:255],
            category_code="OTHER",
            description=str(state.get("description") or ""),
            urgency_code=urgency,
            status_code="CREATED",
        )
        session.add(appeal)
        await session.flush()
        await record_audit(
            session,
            user_id=user.id,
            action_code="appeal.create_vk",
            entity_name="appeals",
            entity_id=appeal.id,
            new_value={"source": "vk", "urgency_code": urgency},
        )
        commanders = list(
            (
                await session.scalars(
                    select(User).where(
                        User.status_code == "ACTIVE",
                        User.role_code.in_(("DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN")),
                    )
                )
            ).all()
        )
        for commander in commanders:
            session.add(
                Notification(
                    user_id=commander.id,
                    type_code="APPEAL",
                    title=f"Новое обращение: {appeal.subject}",
                    body=f"{user.full_name} отправил обращение через VK. Срочность: {urgency}.",
                    entity_name="appeals",
                    entity_id=appeal.id,
                    send_to_tg=True,
                )
            )
        await session.commit()
    await _clear_event_state(message.from_id)
    await message.answer(with_site_link("Обращение отправлено. Ответ придёт в уведомления.", site_url), keyboard=main_keyboard(site_url))


async def _start_normative_submission_from_vk(message, user: User, site_url: str | None) -> bool:
    attachment_text = _serialize_attachments(message)
    if not attachment_text:
        return False
    async with AsyncSessionLocal() as session:
        normatives = list(
            (
                await session.scalars(
                    select(Normative)
                    .where(
                        Normative.is_active.is_(True),
                        (Normative.squad_id.is_(None)) | (Normative.squad_id == user.squad_id),
                    )
                    .order_by(Normative.deadline_at.nullslast(), Normative.id)
                    .limit(8)
                )
            ).all()
        )
    if not normatives:
        await message.answer("Вложение получил, но активных нормативов для сдачи сейчас нет.", keyboard=main_keyboard(site_url))
        return True
    await _set_event_state(
        message.from_id,
        step="normative_attachment",
        attachment_text=attachment_text,
    )
    await message.answer(
        "Это сдача норматива? Выберите норматив для вложения.",
        keyboard=normative_choice_keyboard(normatives),
    )
    return True


async def _handle_normative_submit_payload(message, user: User, payload: dict, site_url: str | None) -> None:
    state = await _get_event_state(message.from_id)
    if not state or state.get("step") != "normative_attachment":
        await message.answer("Пришлите вложение ещё раз и выберите норматив.", keyboard=main_keyboard(site_url))
        return
    try:
        normative_id = int(payload["normative_id"])
    except (KeyError, TypeError, ValueError):
        await message.answer("Не удалось определить норматив.", keyboard=main_keyboard(site_url))
        return

    async with AsyncSessionLocal() as session:
        normative = await session.get(Normative, normative_id)
        if not normative or not normative.is_active:
            await message.answer("Норматив больше недоступен.", keyboard=main_keyboard(site_url))
            await _clear_event_state(message.from_id)
            return
        submission = await submit_normative_service(
            session,
            normative=normative,
            submitter=user,
            status_code="PENDING",
            comment=f"[VK attachment]\n{state.get('attachment_text', '')}",
            file_ids=None,
            audit_action_code="normative_submission.submit_via_vk",
            audit_value={"normative_id": normative.id, "source": "vk"},
            notification_body=f"{user.full_name} прислал вложение в VK по нормативу «{normative.title}».",
            notification_scope="submitter_squad",
        )
        await session.commit()
        await session.refresh(submission)
        normative_title = normative.title
    await _clear_event_state(message.from_id)
    await message.answer(f"Сдача по нормативу «{normative_title}» отправлена командиру.", keyboard=main_keyboard(site_url))


async def _unlink_vk(message, user: User) -> None:
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if db_user is None:
            await message.answer("Аккаунт не найден. Обратитесь к командиру.", keyboard=login_entry_keyboard())
            return
        old_vk = db_user.vk_id
        db_user.vk_id = None
        db_user.updated_at = datetime.now(timezone.utc)
        await record_audit(
            session,
            user_id=db_user.id,
            action_code="vk.unlink_bot",
            entity_name="users",
            entity_id=db_user.id,
            old_value={"vk_id": old_vk},
        )
        await session.commit()
    await _clear_event_state(message.from_id)
    await message.answer("VK отвязан. Чтобы подключить снова, используйте код или вход по паролю.", keyboard=login_entry_keyboard())


async def _try_link(vk_id: int, code: str) -> str | None:
    """Returns greeting on success, error string on failure, None if code invalid."""
    async with AsyncSessionLocal() as session:
        user_id = await redeem_link_code(session, code, channel="VK")
        if user_id is None:
            await session.rollback()
            return None
        existing = await session.scalar(select(User).where(User.vk_id == vk_id))
        if existing is not None and existing.id != user_id:
            await session.rollback()
            return "Этот ВКонтакте уже привязан к другому аккаунту."
        user = await session.get(User, user_id)
        if user is None:
            await session.rollback()
            return "Аккаунт не найден. Обратитесь к командиру."
        if role_level(user.role_code) < RoleLevel.PARTICIPANT:
            await session.rollback()
            return "Привязка доступна только подтверждённым участникам состава."
        if user.vk_id == vk_id:
            await session.rollback()
            return f"Аккаунт уже привязан, {user.full_name}."
        if user.vk_id is not None and user.vk_id != vk_id:
            await session.rollback()
            return "Этот профиль уже привязан к другому аккаунту ВКонтакте."
        user.vk_id = vk_id
        now = datetime.now(timezone.utc)
        user.updated_at = now
        await session.execute(
            update(Notification)
            .where(Notification.user_id == user.id, Notification.vk_sent_at.is_(None))
            .values(vk_sent_at=now)
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return "Этот ВКонтакте уже привязан к другому аккаунту."
        return f"Готово, {user.full_name}! Аккаунт привязан. Теперь вы будете получать уведомления здесь."


async def _try_password_link(vk_id: int, telegram_id: int, password: str) -> tuple[bool, str]:
    """Link VK to an account using its website login (Telegram ID + password)."""
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        # Generic failure message — do not reveal which Telegram IDs exist.
        if user is not None:
            lockout = password_lockout_state(user)
            if lockout.locked:
                return False, "Слишком много неудачных попыток входа. Попробуйте позже."
        if user is None or not user.password_hash or not verify_password(password, user.password_hash):
            if user is not None:
                await register_failed_password_login(session, user)
                await session.commit()
            return False, "Неверный Telegram ID или пароль."
        if user.status_code != "ACTIVE" or role_level(user.role_code) < RoleLevel.PARTICIPANT:
            return False, "Доступ только для подтверждённых участников состава."
        existing = await session.scalar(select(User).where(User.vk_id == vk_id))
        if existing is not None and existing.id != user.id:
            return False, "Этот ВКонтакте уже привязан к другому аккаунту."
        if user.vk_id == vk_id:
            register_successful_password_login(user)
            await session.commit()
            return True, f"Аккаунт уже привязан, {user.full_name}."
        if user.vk_id is not None and user.vk_id != vk_id:
            return False, "Этот профиль уже привязан к другому аккаунту ВКонтакте."
        user.vk_id = vk_id
        register_successful_password_login(user)
        now = datetime.now(timezone.utc)
        user.updated_at = now
        await session.execute(
            update(Notification)
            .where(Notification.user_id == user.id, Notification.vk_sent_at.is_(None))
            .values(vk_sent_at=now)
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False, "Этот ВКонтакте уже привязан к другому аккаунту."
        return True, f"Готово, {user.full_name}! Аккаунт привязан."


def link_instructions(settings) -> str:
    lines = [
        "Привет! Это бот ВПК «Звезда».",
        "",
        "Чтобы пользоваться ботом, привяжите аккаунт. Два способа:",
        "",
        "🔑 По паролю — нажмите «Войти по паролю» и пришлите",
        "   первым сообщением Telegram ID, вторым — пароль",
        "   (тот, что задали в приложении ВПК).",
        "",
        "🔢 По коду — в приложении ВПК: Профиль → «ВКонтакте» →",
        "   «Привязать», и пришлите сюда 6-значный код.",
        "",
        "Доступ только подтверждённым участникам состава.",
    ]
    if settings.bot_username:
        lines.append(f"Ещё не в составе? Telegram-бот: https://t.me/{settings.bot_username}")
    return "\n".join(lines)


def build_bot():
    from vkbottle.bot import Bot, Message

    settings = get_settings()
    bot = Bot(token=settings.vk_group_token)

    @bot.on.message()
    async def handle(message: Message) -> None:
        vk_id = message.from_id
        text = (message.text or "").strip()
        low = text.casefold()
        site = settings.site_url or settings.mini_app_url
        user = await find_user_by_vk(vk_id)

        # Not linked yet — password login dialog, link code, or instructions.
        if user is None:
            if low in {"отмена", "cancel", "/cancel", "стоп"}:
                await _clear_login_state(vk_id)
                await message.answer("Отменено.", keyboard=login_entry_keyboard())
                return

            if "по коду" in low:
                await _clear_login_state(vk_id)
                await message.answer(
                    "Получите 6-значный код в приложении ВПК: Профиль → ВКонтакте → Привязать. "
                    "Затем пришлите код сюда одним сообщением.",
                    keyboard=login_entry_keyboard(),
                )
                return

            state = await _get_login_state(vk_id)

            # Step 2: awaiting password
            if state and state.get("step") == "awaiting_password":
                ok, msg = await _try_password_link(vk_id, state["telegram_id"], text)
                await _clear_login_state(vk_id)
                if ok:
                    await message.answer(
                        with_site_link(msg + "\n\nСовет: удалите сообщение с паролем из переписки.", site),
                        keyboard=main_keyboard(site),
                    )
                else:
                    await message.answer(msg + "\nЧтобы попробовать снова — нажмите «Войти по паролю».", keyboard=login_entry_keyboard())
                return

            # Step 1: awaiting login (Telegram ID)
            if state and state.get("step") == "awaiting_login":
                digits = re.sub(r"\D", "", text)
                if not digits:
                    await message.answer("Введите ваш Telegram ID цифрами (или «отмена»).")
                    return
                await _set_login_state(vk_id, step="awaiting_password", telegram_id=int(digits))
                await message.answer("Теперь пришлите пароль (тот, что задали в приложении ВПК):")
                return

            # Start password login flow
            if "парол" in low or "войти" in low or low in {"начать", "start", "старт"}:
                await _set_login_state(vk_id, step="awaiting_login")
                await message.answer("Введите ваш Telegram ID (это логин):")
                return

            # Link code path (6 digits from the Mini App)
            code_match = _CODE_RE.match(text)
            if code_match:
                result = await _try_link(vk_id, code_match.group(1))
                if result is None:
                    await message.answer("Код неверный или истёк. Получите новый в приложении ВПК.")
                else:
                    await message.answer(with_site_link(result, site), keyboard=main_keyboard(site))
                return

            await message.answer(link_instructions(settings), keyboard=login_entry_keyboard())
            return

        if user.status_code != "ACTIVE" or role_level(user.role_code) < RoleLevel.PARTICIPANT:
            await message.answer("Доступ к боту приостановлен. Обратитесь к командиру.", keyboard=empty_keyboard())
            return

        payload = _message_payload(message.payload)
        action = payload.get("action")
        if low in {"отмена", "cancel", "/cancel", "стоп"}:
            await _clear_event_state(vk_id)
            await message.answer("Действие отменено.", keyboard=main_keyboard(site))
            return
        if action == "event_response":
            await _handle_event_response(message, user, payload, site)
            return
        if action == "absence_reason":
            await _handle_absence_reason(message, user, payload, site)
            return
        if action == "appeal_urgency":
            await _handle_appeal_urgency_payload(message, user, payload, site)
            return
        if action == "norm_submit":
            await _handle_normative_submit_payload(message, user, payload, site)
            return

        event_state = await _get_event_state(vk_id)
        menu_commands = {"расписание", "отметиться", "уведомления", "профиль", "открыть сайт", "меню", "обращение", "сбросить пароль", "отвязать"}
        if event_state and event_state.get("step") == "awaiting_absence_comment":
            if low in menu_commands:
                await _clear_event_state(vk_id)
            elif text:
                await _save_absence_comment(message, user, event_state, text, site)
                return
        if event_state and str(event_state.get("step", "")).startswith("reset_password_"):
            if await _handle_password_reset_state(message, user, event_state, text, site):
                return
            else:
                await message.answer("Напишите причину текстом или нажмите «Отмена».")
                return
        if event_state and str(event_state.get("step", "")).startswith("appeal_"):
            handled = await _handle_appeal_state(message, user, event_state, text, site)
            if handled:
                return

        if await _start_normative_submission_from_vk(message, user, site):
            return

        if "расписан" in low:
            await _send_schedule(message, user, site)
        elif "отмет" in low:
            await _self_checkin_from_vk(message, user, site)
        elif "уведомл" in low:
            await message.answer(await _notifications_text(user), keyboard=main_keyboard(site))
        elif "профиль" in low:
            await message.answer(_profile_text(user), keyboard=main_keyboard(site))
        elif "обращ" in low:
            await _start_appeal(message, user)
        elif "сброс" in low and "парол" in low:
            await _set_event_state(vk_id, step="reset_password_new")
            await message.answer("Введите новый пароль (минимум 8 символов). Для выхода напишите «Отмена».")
        elif "отвяз" in low:
            await _unlink_vk(message, user)
        elif "сайт" in low:
            await message.answer(
                with_site_link("Личный кабинет ВПК:", site),
                keyboard=main_keyboard(site),
            )
        else:
            await message.answer(
                with_site_link(
                    f"С возвращением, {user.full_name}! Выберите раздел:",
                    site,
                ),
                keyboard=main_keyboard(site),
            )

    return bot


async def _idle() -> None:
    import asyncio

    await asyncio.Event().wait()


def main() -> None:
    configure_json_logging()
    settings = get_settings()
    init_sentry(settings, service_name="vk_bot")
    start_heartbeat_thread(settings.vk_bot_heartbeat_path)
    if not settings.vk_bot_enabled or not settings.vk_group_token:
        # Stay alive without polling so the container does not restart-loop when VK is off.
        logger.info("VK bot disabled or token missing; idling.")
        asyncio.run(_idle())
        return
    logger.info("Starting VPK Zvezda VK bot")
    build_bot().run_forever()


if __name__ == "__main__":
    main()
