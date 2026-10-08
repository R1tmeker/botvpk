from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update

from .config import get_settings
from .database import AsyncSessionLocal
from .models import AbsenceReason, Appeal, AppealMessage, EventResponse, Notification, Normative, ScheduleEvent, User
from .roles import RoleLevel, role_level
from .services.auth_security import (
    PasswordPolicyError,
    bump_token_version,
    password_lockout_state,
    register_failed_password_login,
    register_successful_password_login,
    validate_password_policy,
)
from .services.bot_content import attendance_text, checkin_statement, local_time, normative_choices, normatives_text, schedule_card
from .services.bot_navigation import MENU_TEXT, entity_id, menu_rows, page_number
from .services.attendance import SelfCheckInError, self_check_in, sync_automatic_grade
from .services.appeal_policy import APPEAL_STATUS_LABELS, can_access_appeal, validate_appeal_text
from .services.appeals import add_appeal_reply, notify_appeal_commanders, publish_appeal_update
from .services.event_response_policy import EventResponseError, validate_event_available
from .services.notification_inbox import inbox_counts, inbox_page, mark_inbox_read, mark_notification_read
from .services.realtime import publish_realtime_event
from .services.search import search_accessible
from .services.events import respond_to_event
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


def inline_keyboard(rows: list[list[dict]]) -> str:
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


def _link_button(label: str, url: str) -> dict:
    return {"action": {"type": "open_link", "label": label, "link": url}}


def main_keyboard(site_url: str | None = None, role: RoleLevel = RoleLevel.PARTICIPANT) -> str:
    rows = [[_text_button(label, "primary" if action == "schedule" else "secondary", {"action": "menu", "section": action}) for label, action in row] for row in menu_rows(role)]
    rows.append([_text_button("Меню")])
    if site_url:
        rows[-1].append(_link_button("Открыть сайт", site_url))
    return json.dumps({"one_time": False, "buttons": rows}, ensure_ascii=False)


def section_keyboard(user: User, section: str) -> str:
    rows = menu_rows(role_level(user.role_code), section)
    if section == "account":
        rows = [[("Отвязать VK" if action == "vk" else label, "unlink" if action == "vk" else action) for label, action in row] for row in rows]
    return inline_keyboard([[_text_button(label, payload={"action": "menu", "section": action}) for label, action in row] for row in rows])


def _menu_back(section: str = "home") -> dict:
    return _text_button("← Назад", payload={"action": "menu", "section": section})


def cancel_keyboard() -> str:
    return inline_keyboard([[_text_button("← Назад", payload={"action": "dialog_back"}), _text_button("Отмена")], [_text_button("Меню")]])


def navigation_buttons(action: str, page: int, has_next: bool) -> list[dict]:
    buttons = []
    if page:
        buttons.append(_text_button("← Назад", payload={"action": action, "page": page - 1}))
    if has_next:
        buttons.append(_text_button("Далее →", payload={"action": action, "page": page + 1}))
    return buttons


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


async def _self_checkin_from_vk(message, user: User, site_url: str | None, event_id: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        events = list((await session.scalars(checkin_statement(user, now, event_id))).all())
        if len(events) > 1:
            rows = [[_text_button(event.title[:40], payload={"action": "checkin", "event_id": event.id})] for event in events[:8]]
            await message.answer("На каком занятии вы присутствуете?\n" + "\n".join(f"• {event.title[:120]} · {local_time(event.start_datetime)}" for event in events[:8]), keyboard=inline_keyboard(rows[:5] + [[_text_button("Меню")]]))
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
    buttons.append([_text_button("← Назад", payload={"action": "dialog_back"}), _text_button("Отмена", "negative")])
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
                [_text_button("← Назад", payload={"action": "dialog_back"}), _text_button("Отмена", "negative")],
            ],
        },
        ensure_ascii=False,
    )


def normative_choice_keyboard(normatives: list[Normative], page: int = 0) -> str:
    buttons = [
        [
            _text_button(
                normative.title[:40],
                "secondary",
                {"action": "norm_submit", "normative_id": normative.id},
            )
        ]
        for normative in normatives[:5]
    ]
    nav = navigation_buttons("norm_choice_page", page, len(normatives) > 5)
    if nav:
        buttons.append(nav)
    buttons.append([_text_button("← Назад", payload={"action": "dialog_back"}), _text_button("Отмена", "negative")])
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


async def _send_schedule(message, user: User, site_url: str | None, prefix: str | None = None, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        event, text, actionable, has_next = await schedule_card(session, user, page)
    rows = []
    if event and actionable:
        base = {"action": "event_response", "event_id": event.id}
        rows = [[_text_button("Приду", "positive", {**base, "response_code": "COMING"}),
                 _text_button("Не приду", "negative", {**base, "response_code": "NOT_COMING"})],
                [_text_button("Уточню", payload={**base, "response_code": "MAYBE"})]]
    nav = navigation_buttons("schedule_page", page, has_next)
    if nav:
        rows.append(nav)
    rows.append([_menu_back()])
    await message.answer(f"{prefix}\n\n{text}" if prefix else text, keyboard=inline_keyboard(rows))


async def _event_for_response(session, user: User, event_id: int) -> tuple[ScheduleEvent | None, str | None]:
    event = await session.scalar(select(ScheduleEvent).where(ScheduleEvent.id == event_id).with_for_update())
    if event is None:
        return None, "Занятие не найдено. Обновите расписание."
    try:
        validate_event_available(event, role=role_level(user.role_code), squad_id=user.squad_id, now=datetime.now(timezone.utc))
    except EventResponseError as exc:
        return None, str(exc)
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
    await respond_to_event(
        session,
        event=event,
        user_id=user.id,
        role=role_level(user.role_code),
        squad_id=user.squad_id,
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
    event_id = entity_id(payload.get("event_id"))
    if event_id is None:
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

    await publish_realtime_event(get_settings(), event_type="schedule.response.updated", user_id=user.id, query_keys=["schedule", "dashboard"])
    await _send_schedule(
        message,
        user,
        site_url,
        prefix=f"Ответ сохранён: {_RESPONSE_LABELS[response_code].lower()}.",
    )


async def _handle_absence_reason(message, user: User, payload: dict, site_url: str | None) -> None:
    event_id = entity_id(payload.get("event_id"))
    reason_id = entity_id(payload.get("reason_id"))
    if event_id is None or reason_id is None:
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

    await publish_realtime_event(get_settings(), event_type="schedule.response.updated", user_id=user.id, query_keys=["schedule", "dashboard"])
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
    await publish_realtime_event(get_settings(), event_type="schedule.response.updated", user_id=user.id, query_keys=["schedule", "dashboard"])
    await _send_schedule(
        message,
        user,
        site_url,
        prefix=f"Ответ сохранён: не приду. Причина: {state.get('reason_label')}: {comment}.",
    )


async def _send_notifications(message, user: User, page: int = 0, unread: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        counts = await inbox_counts(session, user.id)
        items = await inbox_page(session, user.id, unread_only=unread, offset=page * 3, limit=4)
    lines = [f"Уведомления: {counts['unread']} непрочитанных из {counts['total']}."]
    rows = []
    for number, item in enumerate(items[:3], 1):
        lines.append(f"{number}. {'●' if not item.is_read else '○'} {item.title[:160]}")
        rows.append([_text_button(f"{number}. Открыть", payload={"action": "inbox_view", "id": item.id, "page": page, "unread": unread})])
    if not items:
        lines.append("Непрочитанных уведомлений нет." if unread else "На этой странице уведомлений нет.")
    nav = navigation_buttons("inbox_page", page, len(items) > 3)
    for button in nav:
        payload = json.loads(button["action"]["payload"])
        button["action"]["payload"] = json.dumps({**payload, "unread": unread})
    if nav:
        rows.append(nav)
    modes = [_text_button("Все" if unread else "Непрочитанные", payload={"action": "inbox_page", "page": 0, "unread": not unread})]
    if counts['unread']:
        modes.append(_text_button("Прочитать все", payload={"action": "inbox_readall"}))
    rows.extend([modes, [_menu_back()]])
    await message.answer("\n".join(lines), keyboard=inline_keyboard(rows))


async def _send_notification(message, user: User, payload: dict, site_url: str | None) -> None:
    item_id = entity_id(payload.get("id"))
    if not item_id:
        await message.answer("Кнопка устарела. Откройте уведомления заново.")
        return
    async with AsyncSessionLocal() as session:
        item = await mark_notification_read(session, user.id, item_id)
        if item is None:
            await message.answer("Уведомление недоступно.")
            return
        await session.commit()
    rows = []
    if item.entity_name == "appeals" and item.entity_id:
        rows.append([_text_button("Переписка", payload={"action": "appeal_thread", "id": item.entity_id, "page": 0})])
    if site_url and item.deep_link:
        from urllib.parse import urljoin
        if item.deep_link.startswith("/") and not item.deep_link.startswith("//") and "\\" not in item.deep_link:
            rows.append([_link_button("Открыть на сайте", urljoin(site_url.rstrip("/") + "/", item.deep_link.lstrip("/")))])
    rows.append([_text_button("← Назад", payload={"action": "inbox_page", "page": page_number(payload.get("page", 0)) or 0, "unread": payload.get("unread") is True})])
    await message.answer(f"{item.title[:255]}\n{local_time(item.created_at)}\n\n{(item.body or 'Без дополнительного текста.')[:3000]}", keyboard=inline_keyboard(rows))
    await publish_realtime_event(get_settings(), event_type="notifications.read", user_id=user.id, query_keys=["notifications", "dashboard"])


async def _send_my_appeals(message, user: User, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        items = list((await session.scalars(select(Appeal).where(Appeal.author_user_id == user.id)
            .order_by(Appeal.created_at.desc(), Appeal.id.desc()).offset(page * 4).limit(5))).all())
    lines = [f"Мои обращения · страница {page + 1}"]
    rows = []
    for item in items[:4]:
        lines.append(f"#{item.id} · {item.subject[:180]}\n{APPEAL_STATUS_LABELS.get(item.status_code, item.status_code)}")
        rows.append([_text_button(f"#{item.id} Переписка", payload={"action": "appeal_thread", "id": item.id, "page": 0})])
    if not items:
        lines.append("Обращений на этой странице нет.")
    nav = navigation_buttons("appeals_page", page, len(items) > 4)
    if nav:
        rows.append(nav)
    rows.append([_text_button("Новое обращение", payload={"action": "menu", "section": "appeal"}), _menu_back("contact")])
    await message.answer("\n".join(lines), keyboard=inline_keyboard(rows))


async def _accessible_appeal(session, user: User, appeal_id: int):
    appeal = await session.scalar(select(Appeal).where(Appeal.id == appeal_id).with_for_update())
    return appeal if appeal and can_access_appeal(author_id=appeal.author_user_id, user_id=user.id, role=role_level(user.role_code)) else None


async def _send_appeal_thread(message, user: User, appeal_id: int, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        appeal = await _accessible_appeal(session, user, appeal_id)
        if appeal is None:
            await message.answer("Обращение не найдено или недоступно.")
            return
        items = list((await session.scalars(select(AppealMessage).where(AppealMessage.appeal_id == appeal.id)
            .order_by(AppealMessage.created_at.desc(), AppealMessage.id.desc()).offset(page * 3).limit(4))).all())
    await message.answer(f"#{appeal.id} · {appeal.subject}\n{APPEAL_STATUS_LABELS.get(appeal.status_code, appeal.status_code)}")
    if page == 0:
        for label, body in (("Описание", appeal.description), ("Решение", appeal.resolution_text)):
            for start in range(0, len(body or ''), 3000):
                await message.answer(f"{label}:\n{body[start:start + 3000]}")
    for item in reversed(items[:3]):
        label = "Вы" if item.author_id == user.id else "Командование" if item.author_id != appeal.author_user_id else "Автор"
        for start in range(0, len(item.body), 3000):
            await message.answer(f"{label} · {local_time(item.created_at)}\n{item.body[start:start + 3000]}")
    rows = [[_text_button("Ответить", payload={"action": "appeal_reply", "id": appeal.id})]]
    nav = navigation_buttons("appeal_thread", page, len(items) > 3)
    for button in nav:
        value = json.loads(button["action"]["payload"])
        button["action"]["payload"] = json.dumps({**value, "id": appeal.id})
    if nav:
        rows.append(nav)
    rows.append([_text_button("← Назад", payload={"action": "appeals_page", "page": 0}), _text_button("Меню")])
    await message.answer("Можно ответить прямо здесь.", keyboard=inline_keyboard(rows))


async def _save_appeal_reply(message, user: User, state: dict, text: str, site_url: str | None) -> None:
    try:
        body = validate_appeal_text(text)
    except ValueError as exc:
        await message.answer(str(exc), keyboard=cancel_keyboard())
        return
    async with AsyncSessionLocal() as session:
        appeal = await _accessible_appeal(session, user, state['appeal_id'])
        if appeal is None or state.get('user_id') != user.id:
            await _clear_event_state(message.from_id)
            await message.answer("Обращение недоступно. Откройте его заново.")
            return
        await add_appeal_reply(session, appeal, sender_id=user.id, role=role_level(user.role_code), body=body)
        await session.commit()
    await _clear_event_state(message.from_id)
    await publish_appeal_update()
    await message.answer("Ответ отправлен.")
    await _send_appeal_thread(message, user, state['appeal_id'])


async def _send_normatives(message, user: User, page: int = 0) -> None:
    async with AsyncSessionLocal() as session:
        text, has_next = await normatives_text(session, user, page)
    nav = navigation_buttons("normatives_page", page, has_next)
    rows = ([nav] if nav else []) + [[_menu_back()]]
    await message.answer(text, keyboard=inline_keyboard(rows))



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
    await message.answer("Напишите тему обращения одним сообщением.", keyboard=cancel_keyboard())


async def _handle_appeal_state(message, user: User, state: dict, text: str, site_url: str | None) -> bool:
    step = state.get("step")
    if step == "appeal_subject":
        subject = text.strip()
        if not 3 <= len(subject) <= 255:
            await message.answer("Тема должна содержать от 3 до 255 символов.")
            return True
        await _set_event_state(message.from_id, step="appeal_description", subject=subject, description=state.get("description"))
        await message.answer("Теперь опишите ситуацию. Это сообщение уйдёт командирам.", keyboard=cancel_keyboard())
        return True

    if step == "appeal_description":
        description = text.strip()
        if not 5 <= len(description) <= 4000:
            await message.answer("Описание должно содержать от 5 до 4000 символов.")
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
        urgency = {"обычная": "NORMAL", "срочная": "HIGH", "очень срочно": "URGENT"}.get(text.casefold())
        if urgency is None:
            await message.answer("Выберите срочность кнопкой.", keyboard=appeal_urgency_keyboard())
            return True
        await _create_appeal_from_vk(message, user, state, urgency, site_url)
        return True

    return False


async def _handle_appeal_urgency_payload(message, user: User, payload: dict, site_url: str | None) -> None:
    state = await _get_event_state(message.from_id)
    if not state or state.get("step") != "appeal_urgency":
        await message.answer("Начните обращение кнопкой «Обращение».", keyboard=main_keyboard(site_url))
        return
    urgency = str(payload.get("urgency") or "")
    if urgency not in {"NORMAL", "HIGH", "URGENT"}:
        await message.answer("Выберите срочность кнопкой.", keyboard=appeal_urgency_keyboard())
        return
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
        await notify_appeal_commanders(session, appeal, sender_id=user.id, title=f"Новое обращение: {appeal.subject}",
            body=f"{user.full_name} отправил обращение через VK. Срочность: {urgency}.")
        await session.commit()
    await _clear_event_state(message.from_id)
    await publish_appeal_update()
    await message.answer(f"Обращение #{appeal.id} отправлено. Ответ придёт в уведомления.", keyboard=inline_keyboard([[_text_button("Переписка", payload={"action": "appeal_thread", "id": appeal.id, "page": 0}), _text_button("Меню")]]))


async def _start_normative_submission_from_vk(message, user: User, site_url: str | None) -> bool:
    attachment_text = _serialize_attachments(message)
    if not attachment_text:
        return False
    async with AsyncSessionLocal() as session:
        normatives = await normative_choices(session, user)
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
    normative_id = entity_id(payload.get("normative_id"))
    if normative_id is None:
        await message.answer("Не удалось определить норматив.", keyboard=main_keyboard(site_url))
        return

    async with AsyncSessionLocal() as session:
        normative = await session.get(Normative, normative_id)
        if not normative or not normative.is_active or (normative.squad_id is not None and normative.squad_id != user.squad_id):
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


async def _handle_menu(message, user: User, section: str, site_url: str | None) -> None:
    role = role_level(user.role_code)
    if section in MENU_TEXT:
        if section == "command" and role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
            await message.answer("Доступ только командирам.")
            return
        await message.answer(MENU_TEXT[section], keyboard=main_keyboard(site_url, role) if section == "home" else section_keyboard(user, section))
    elif section == "schedule":
        await _send_schedule(message, user, site_url)
    elif section == "checkin":
        await _self_checkin_from_vk(message, user, site_url)
    elif section == "notifications":
        await _send_notifications(message, user)
    elif section == "normatives":
        await _send_normatives(message, user)
    elif section == "attendance":
        async with AsyncSessionLocal() as session:
            text = await attendance_text(session, user)
        await message.answer(text, keyboard=inline_keyboard([[_menu_back("personal")]]))
    elif section == "profile":
        await message.answer(_profile_text(user), keyboard=inline_keyboard([[_menu_back("personal")]]))
    elif section == "appeal":
        await _start_appeal(message, user)
    elif section == "myappeals":
        await _send_my_appeals(message, user)
    elif section == "search":
        await _set_event_state(message.from_id, step="search")
        await message.answer("Что найти? Напишите от 2 до 100 символов: занятие, норматив, материал или участник.", keyboard=cancel_keyboard())
    elif section == "password":
        await _set_event_state(message.from_id, step="reset_password_new")
        await message.answer("Введите новый пароль сайта (минимум 8 символов). Для выхода — «Отмена» или «Меню».", keyboard=cancel_keyboard())
    elif section == "unlink":
        await _set_event_state(message.from_id, step="unlink_confirm", user_id=user.id)
        await message.answer("Отвязать этот VK от профиля ВПК? Уведомления ВПК в VK перестанут приходить. Telegram и данные профиля сохранятся.", keyboard=inline_keyboard([[_text_button("Да, отвязать", "negative", {"action": "unlink_confirm"}), _text_button("Отмена")]]))
    elif section == "my_id":
        await message.answer(f"Ваш VK ID: {message.from_id}\nTelegram ID: {user.telegram_id or 'не привязан'}", keyboard=inline_keyboard([[_menu_back("account")]]))
    elif section == "vk":
        await message.answer("Этот VK уже подключён к вашему профилю.", keyboard=inline_keyboard([[_menu_back("account")]]))
    elif section in {"applications", "journal", "admin", "site"}:
        if section != "site" and role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
            await message.answer("Доступ только командирам.")
            return
        paths = {"applications": "/admin/applications", "journal": "/attendance", "admin": "/admin", "site": "/"}
        rows = [[_link_button("Открыть раздел", site_url.rstrip("/") + paths[section])]] if site_url else []
        rows.append([_menu_back()])
        text = "Управление ВПК:" if site_url else "Адрес сайта пока не настроен. Обратитесь к администратору."
        if section == "applications":
            from .models import JoinApplication
            async with AsyncSessionLocal() as session:
                items = list((await session.scalars(select(JoinApplication).where(JoinApplication.status_code.not_in(["ACCEPTED", "REJECTED", "ARCHIVED"]))
                    .order_by(JoinApplication.created_at.desc()).limit(10))).all())
            text = "Последние активные заявки:\n" + "\n".join(f"• {item.full_name[:120]} · {item.status_code}" for item in items) if items else "Активных заявок нет."
        await message.answer(text, keyboard=inline_keyboard(rows))
    else:
        await message.answer("Раздел недоступен. Откройте меню.", keyboard=main_keyboard(site_url, role))


async def _handle_payload(message, user: User, payload: dict, site_url: str | None) -> None:
    action = payload.get("action")
    if not isinstance(action, str):
        await message.answer("Некорректная кнопка. Откройте меню заново.")
        return
    if action == "norm_choice_page":
        state = await _get_event_state(message.from_id)
        page = page_number(payload.get("page", 0))
        if not state or state.get("step") != "normative_attachment" or page is None:
            await message.answer("Пришлите вложение заново.")
            return
        async with AsyncSessionLocal() as session:
            rows = await normative_choices(session, user, page)
        await message.answer("Выберите норматив для ранее присланного вложения:", keyboard=normative_choice_keyboard(rows, page))
        return
    if action in {"event_response", "absence_reason", "appeal_urgency", "norm_submit"}:
        # An old button must not accidentally finish a different text dialog.
        if action == "event_response":
            await _clear_event_state(message.from_id)
        handlers = {"event_response": _handle_event_response, "absence_reason": _handle_absence_reason,
                    "appeal_urgency": _handle_appeal_urgency_payload, "norm_submit": _handle_normative_submit_payload}
        try:
            await handlers[action](message, user, payload, site_url)
        except EventResponseError as exc:
            await message.answer(str(exc), keyboard=cancel_keyboard())
        return
    if action in {"schedule_page", "normatives_page", "inbox_page", "appeals_page", "appeal_thread"}:
        page = page_number(payload.get("page", 0))
        if page is None:
            await message.answer("Кнопка устарела. Откройте раздел заново.")
            return
        await _clear_event_state(message.from_id)
        if action == "schedule_page":
            await _send_schedule(message, user, site_url, page=page)
        elif action == "normatives_page":
            await _send_normatives(message, user, page)
        elif action == "inbox_page":
            await _send_notifications(message, user, page, payload.get("unread") is True)
        elif action == "appeals_page":
            await _send_my_appeals(message, user, page)
        else:
            appeal_id = entity_id(payload.get("id"))
            if appeal_id:
                await _send_appeal_thread(message, user, appeal_id, page)
            else:
                await message.answer("Обращение не найдено.")
    elif action == "checkin":
        event_id = entity_id(payload.get("event_id"))
        if event_id:
            await _clear_event_state(message.from_id)
            await _self_checkin_from_vk(message, user, site_url, event_id)
        else:
            await message.answer("Занятие не найдено. Откройте самоотметку заново.")
    elif action == "inbox_view":
        await _clear_event_state(message.from_id)
        await _send_notification(message, user, payload, site_url)
    elif action == "inbox_readall":
        async with AsyncSessionLocal() as session:
            count = await mark_inbox_read(session, user.id)
            await record_audit(session, user_id=user.id, action_code="notifications.read_all", entity_name="notifications", new_value={"count": count, "source": "VK"})
            await session.commit()
        await publish_realtime_event(get_settings(), event_type="notifications.read", user_id=user.id, query_keys=["notifications", "dashboard"])
        await _send_notifications(message, user)
    elif action == "appeal_reply":
        appeal_id = entity_id(payload.get("id"))
        async with AsyncSessionLocal() as session:
            appeal = await _accessible_appeal(session, user, appeal_id) if appeal_id else None
        if appeal is None:
            await message.answer("Обращение недоступно.")
            return
        await _set_event_state(message.from_id, step="appeal_reply", appeal_id=appeal.id, user_id=user.id)
        await message.answer(f"Напишите ответ на обращение #{appeal.id} одним сообщением (до 4000 символов).", keyboard=cancel_keyboard())
    elif action == "unlink_confirm":
        state = await _get_event_state(message.from_id)
        if not state or state.get("step") != "unlink_confirm" or state.get("user_id") != user.id:
            await message.answer("Подтверждение устарело. Откройте «Мои данные → Аккаунт» заново.")
            return
        await _clear_event_state(message.from_id)
        await _unlink_vk(message, user)
    else:
        await message.answer("Кнопка устарела. Откройте меню заново.", keyboard=main_keyboard(site_url, role_level(user.role_code)))


async def _send_search(message, user: User, query: str, site_url: str | None) -> None:
    async with AsyncSessionLocal() as session:
        items = await search_accessible(session, query, role=role_level(user.role_code), role_code=user.role_code, squad_id=user.squad_id, user_id=user.id, limit=5)
    lines = [f"Найдено по запросу «{query}»:"] if items else ["Ничего доступного не найдено. Попробуйте другой запрос."]
    rows = []
    for number, item in enumerate(items, 1):
        lines.append(f"{number}. {item.title[:160]}\n{(item.description or '')[:200]}")
        if site_url:
            rows.append([_link_button(f"{number}. Открыть", site_url.rstrip("/") + item.deep_link)])
    rows.append([_text_button("Искать ещё", payload={"action": "menu", "section": "search"}), _text_button("Меню")])
    await message.answer("\n".join(lines), keyboard=inline_keyboard(rows))


async def _go_back(message, user: User, site_url: str | None) -> None:
    state = await _get_event_state(message.from_id) or {}
    step = state.get("step")
    data = {key: value for key, value in state.items() if key not in {"step", "ts"}}
    if step == "appeal_description":
        await _set_event_state(message.from_id, step="appeal_subject", **data)
        await message.answer(f"Тема обращения. Ранее: {state.get('subject', '')}\nНапишите новое значение или повторите прежнее.", keyboard=cancel_keyboard())
    elif step == "appeal_urgency":
        await _set_event_state(message.from_id, step="appeal_description", **data)
        await message.answer(f"Описание обращения. Ранее: {str(state.get('description', ''))[:2500]}\nНапишите новое значение или повторите прежнее.", keyboard=cancel_keyboard())
    elif step == "reset_password_confirm":
        await _set_event_state(message.from_id, step="reset_password_new")
        await message.answer("Введите новый пароль заново.", keyboard=cancel_keyboard())
    elif step == "appeal_reply":
        await _clear_event_state(message.from_id)
        await _send_appeal_thread(message, user, state['appeal_id'])
    elif step == "awaiting_absence_comment":
        async with AsyncSessionLocal() as session:
            event, error = await _event_for_response(session, user, state['event_id'])
            reasons = list((await session.scalars(select(AbsenceReason).where(AbsenceReason.is_active.is_(True)).order_by(AbsenceReason.sort_order))).all()) if event else []
        await _clear_event_state(message.from_id)
        if event and reasons:
            await message.answer("Выберите причину отсутствия:", keyboard=absence_reasons_keyboard(event.id, reasons))
        else:
            await _send_schedule(message, user, site_url, prefix=error)
    elif step == "normative_attachment":
        await _send_normatives(message, user)
        await message.answer("Вложение сохранено. Можно продолжить выбор или прислать другое.", keyboard=inline_keyboard([[_text_button("Выбрать для файла", payload={"action": "norm_choice_page", "page": 0}), _menu_back("home")]]))
    else:
        parent = "contact" if step == "appeal_subject" else "account" if step in {"reset_password_new", "unlink_confirm"} else "personal" if step == "search" else "home"
        await _clear_event_state(message.from_id)
        await _handle_menu(message, user, parent, site_url)


async def handle_message(message) -> None:
    settings = get_settings()
    vk_id = message.from_id
    text = (message.text or "").strip()
    low = text.casefold()
    site = settings.site_url or settings.mini_app_url
    if getattr(message, "peer_id", vk_id) != vk_id:
        await message.answer("Для личных данных и действий напишите сообществу в личные сообщения.")
        return
    user = await find_user_by_vk(vk_id)

    # Not linked yet — password login dialog, link code, or instructions.
    if user is None:
        if low in {"отмена", "cancel", "/cancel", "стоп"}:
            await _clear_login_state(vk_id)
            await message.answer("Отменено.", keyboard=login_entry_keyboard())
            return

        if low == "войти по коду":
            await _clear_login_state(vk_id)
            await message.answer(
                "Получите 6-значный код в приложении ВПК: Профиль → ВКонтакте → Привязать. "
                "Затем пришлите код сюда одним сообщением.",
                keyboard=login_entry_keyboard(),
            )
            return

        if low in {"меню", "начать", "start", "/start", "старт"}:
            await _clear_login_state(vk_id)
            await message.answer(link_instructions(settings), keyboard=login_entry_keyboard())
            return
        if low == "войти по паролю":
            await _set_login_state(vk_id, step="awaiting_login")
            await message.answer("Введите ваш Telegram ID (это логин). Для выхода — «Отмена».", keyboard=cancel_keyboard())
            return
        state = await _get_login_state(vk_id)

        payload = _message_payload(getattr(message, "payload", None))
        if low in {"назад", "← назад", "/back"} or payload.get("action") == "dialog_back":
            if state and state.get("step") == "awaiting_password":
                await _set_login_state(vk_id, step="awaiting_login")
                await message.answer("Введите Telegram ID заново.", keyboard=cancel_keyboard())
            else:
                await _clear_login_state(vk_id)
                await message.answer(link_instructions(settings), keyboard=login_entry_keyboard())
            return

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
            digits = text.strip()
            if not digits.isascii() or not digits.isdigit() or not 1 <= len(digits) <= 16:
                await message.answer("Введите ваш Telegram ID цифрами (или «отмена»).")
                return
            await _set_login_state(vk_id, step="awaiting_password", telegram_id=int(digits))
            await message.answer("Теперь пришлите пароль (тот, что задали в приложении ВПК):")
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

    payload = _message_payload(getattr(message, "payload", None))
    action = payload.get("action")
    aliases = {"меню": "home", "главное меню": "home", "начать": "home", "start": "home", "/start": "home", "старт": "home",
               "расписание": "schedule", "отметиться": "checkin", "уведомления": "notifications", "нормативы": "normatives",
               "мои данные": "personal", "профиль": "profile", "моя явка": "attendance", "связь": "contact", "обращение": "appeal",
               "мои обращения": "myappeals", "поиск": "search", "сбросить пароль": "password", "сменить пароль": "password",
               "отвязать": "unlink", "отвязать vk": "unlink", "мой id": "my_id", "аккаунт": "account", "командиру": "command", "открыть сайт": "site"}
    section = payload.get("section") if action == "menu" else aliases.get(low)
    if low in {"назад", "← назад", "/back"} or action == "dialog_back":
        await _go_back(message, user, site)
        return
    if low in {"отмена", "cancel", "/cancel", "стоп"}:
        await _clear_event_state(vk_id)
        await message.answer("Действие отменено.", keyboard=main_keyboard(site, role_level(user.role_code)))
        return
    if section:
        await _clear_event_state(vk_id)
        await _handle_menu(message, user, str(section), site)
        return
    if action:
        await _handle_payload(message, user, payload, site)
        return
    if low.startswith("/"):
        await message.answer("Команда не отправлена как текст. Используйте «Меню» или «Отмена».", keyboard=cancel_keyboard())
        return
    event_state = await _get_event_state(vk_id)
    if event_state:
        step = str(event_state.get("step", ""))
        if step == "awaiting_absence_comment":
            if not 1 <= len(text) <= 500:
                await message.answer("Напишите причину от 1 до 500 символов.", keyboard=cancel_keyboard())
            else:
                await _save_absence_comment(message, user, event_state, text, site)
            return
        if step.startswith("reset_password_"):
            await _handle_password_reset_state(message, user, event_state, text, site)
            return
        if step == "appeal_reply":
            await _save_appeal_reply(message, user, event_state, text, site)
            return
        if step.startswith("appeal_"):
            await _handle_appeal_state(message, user, event_state, text, site)
            return
        if step == "search":
            if not 2 <= len(text) <= 100:
                await message.answer("Напишите запрос от 2 до 100 символов.", keyboard=cancel_keyboard())
                return
            await _clear_event_state(vk_id)
            await _send_search(message, user, text, site)
            return
        if step == "unlink_confirm":
            await message.answer("Подтвердите отвязку кнопкой или нажмите «Отмена».", keyboard=cancel_keyboard())
            return
    if await _start_normative_submission_from_vk(message, user, site):
        return
    await message.answer("Не понял запрос. Выберите действие кнопкой. Поиск и обращение открывают ввод текста.", keyboard=main_keyboard(site, role_level(user.role_code)))



def build_bot():
    from vkbottle.bot import Bot
    bot = Bot(token=get_settings().vk_group_token)
    bot.on.message()(handle_message)

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
