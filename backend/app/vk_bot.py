from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, update

from .config import get_settings
from .database import AsyncSessionLocal
from .models import AbsenceReason, EventResponse, Notification, ScheduleEvent, User
from .roles import RoleLevel, role_level
from .utils.audit import record_audit
from .utils.channel_link import redeem_link_code
from .utils.password import verify_password

logger = logging.getLogger(__name__)

# Short-lived in-memory login-dialog state per VK user.
# Lost on restart — acceptable for a quick two-message login.
_vk_login_state: dict[int, dict] = {}
_vk_event_state: dict[int, dict] = {}
_LOGIN_STATE_TTL_SECONDS = 600


def _get_login_state(vk_id: int) -> dict | None:
    state = _vk_login_state.get(vk_id)
    if not state:
        return None
    age = (datetime.now(timezone.utc) - state["ts"]).total_seconds()
    if age > _LOGIN_STATE_TTL_SECONDS:
        _vk_login_state.pop(vk_id, None)
        return None
    return state


def _set_login_state(vk_id: int, **data) -> None:
    _vk_login_state[vk_id] = {**data, "ts": datetime.now(timezone.utc)}


def _get_event_state(vk_id: int) -> dict | None:
    state = _vk_event_state.get(vk_id)
    if not state:
        return None
    age = (datetime.now(timezone.utc) - state["ts"]).total_seconds()
    if age > _LOGIN_STATE_TTL_SECONDS:
        _vk_event_state.pop(vk_id, None)
        return None
    return state


def _set_event_state(vk_id: int, **data) -> None:
    _vk_event_state[vk_id] = {**data, "ts": datetime.now(timezone.utc)}

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
        [_text_button("Уведомления")],
        [_text_button("Профиль")],
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
    response = await session.scalar(
        select(EventResponse).where(EventResponse.event_id == event.id, EventResponse.user_id == user.id)
    )
    old_value = None
    if response is None:
        response = EventResponse(event_id=event.id, user_id=user.id)
        session.add(response)
    else:
        old_value = {
            "response_code": response.response_code,
            "absence_reason_id": response.absence_reason_id,
            "custom_reason": response.custom_reason,
        }
    response.response_code = response_code
    response.absence_reason_id = absence_reason_id
    response.custom_reason = custom_reason
    response.responded_at = datetime.now(timezone.utc)
    response.source_code = "VK"
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
                _set_event_state(
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
            _set_event_state(
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
            _vk_event_state.pop(message.from_id, None)
            await message.answer(error or "Занятие недоступно.")
            return
        reason_id = state.get("reason_id")
        if reason_id is not None:
            reason = await session.get(AbsenceReason, int(reason_id))
            if reason is None or not reason.is_active:
                _vk_event_state.pop(message.from_id, None)
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
    _vk_event_state.pop(message.from_id, None)
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
        user.vk_id = vk_id
        now = datetime.now(timezone.utc)
        user.updated_at = now
        await session.execute(
            update(Notification)
            .where(Notification.user_id == user.id, Notification.vk_sent_at.is_(None))
            .values(vk_sent_at=now)
        )
        await session.commit()
        return f"Готово, {user.full_name}! Аккаунт привязан. Теперь вы будете получать уведомления здесь."


async def _try_password_link(vk_id: int, telegram_id: int, password: str) -> tuple[bool, str]:
    """Link VK to an account using its website login (Telegram ID + password)."""
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        # Generic failure message — do not reveal which Telegram IDs exist.
        if user is None or not user.password_hash or not verify_password(password, user.password_hash):
            return False, "Неверный Telegram ID или пароль."
        if user.status_code != "ACTIVE" or role_level(user.role_code) < RoleLevel.PARTICIPANT:
            return False, "Доступ только для подтверждённых участников состава."
        existing = await session.scalar(select(User).where(User.vk_id == vk_id))
        if existing is not None and existing.id != user.id:
            return False, "Этот ВКонтакте уже привязан к другому аккаунту."
        user.vk_id = vk_id
        now = datetime.now(timezone.utc)
        user.updated_at = now
        await session.execute(
            update(Notification)
            .where(Notification.user_id == user.id, Notification.vk_sent_at.is_(None))
            .values(vk_sent_at=now)
        )
        await session.commit()
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
                _vk_login_state.pop(vk_id, None)
                await message.answer("Отменено.", keyboard=login_entry_keyboard())
                return

            if "по коду" in low:
                _vk_login_state.pop(vk_id, None)
                await message.answer(
                    "Получите 6-значный код в приложении ВПК: Профиль → ВКонтакте → Привязать. "
                    "Затем пришлите код сюда одним сообщением.",
                    keyboard=login_entry_keyboard(),
                )
                return

            state = _get_login_state(vk_id)

            # Step 2: awaiting password
            if state and state.get("step") == "awaiting_password":
                ok, msg = await _try_password_link(vk_id, state["telegram_id"], text)
                _vk_login_state.pop(vk_id, None)
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
                _set_login_state(vk_id, step="awaiting_password", telegram_id=int(digits))
                await message.answer("Теперь пришлите пароль (тот, что задали в приложении ВПК):")
                return

            # Start password login flow
            if "парол" in low or "войти" in low or low in {"начать", "start", "старт"}:
                _set_login_state(vk_id, step="awaiting_login")
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
            _vk_event_state.pop(vk_id, None)
            await message.answer("Действие отменено.", keyboard=main_keyboard(site))
            return
        if action == "event_response":
            await _handle_event_response(message, user, payload, site)
            return
        if action == "absence_reason":
            await _handle_absence_reason(message, user, payload, site)
            return

        event_state = _get_event_state(vk_id)
        menu_commands = {"расписание", "уведомления", "профиль", "открыть сайт", "меню"}
        if event_state and event_state.get("step") == "awaiting_absence_comment":
            if low in menu_commands:
                _vk_event_state.pop(vk_id, None)
            elif text:
                await _save_absence_comment(message, user, event_state, text, site)
                return
            else:
                await message.answer("Напишите причину текстом или нажмите «Отмена».")
                return

        if "расписан" in low:
            await _send_schedule(message, user, site)
        elif "уведомл" in low:
            await message.answer(await _notifications_text(user), keyboard=main_keyboard(site))
        elif "профиль" in low:
            await message.answer(_profile_text(user), keyboard=main_keyboard(site))
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
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.vk_bot_enabled or not settings.vk_group_token:
        # Stay alive without polling so the container does not restart-loop when VK is off.
        import asyncio

        logger.info("VK bot disabled or token missing; idling.")
        asyncio.run(_idle())
        return
    logger.info("Starting VPK Zvezda VK bot")
    build_bot().run_forever()


if __name__ == "__main__":
    main()
