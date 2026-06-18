from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, update

from .config import get_settings
from .database import AsyncSessionLocal
from .models import Notification, ScheduleEvent, User
from .roles import RoleLevel, role_level
from .utils.channel_link import redeem_link_code
from .utils.password import verify_password

logger = logging.getLogger(__name__)

# Short-lived in-memory login-dialog state per VK user.
# Lost on restart — acceptable for a quick two-message login.
_vk_login_state: dict[int, dict] = {}
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


def main_keyboard() -> str:
    buttons = [
        [{"action": {"type": "text", "label": "📅 Расписание"}, "color": "primary"}],
        [{"action": {"type": "text", "label": "🔔 Уведомления"}, "color": "secondary"}],
        [{"action": {"type": "text", "label": "👤 Профиль"}, "color": "secondary"}],
    ]
    return json.dumps({"one_time": False, "buttons": buttons}, ensure_ascii=False)


def with_site_link(text: str, site_url: str | None) -> str:
    if not site_url:
        return text
    return f"{text}\n\nСайт: {site_url}"


def empty_keyboard() -> str:
    return json.dumps({"buttons": [], "one_time": True}, ensure_ascii=False)


def login_entry_keyboard() -> str:
    return json.dumps(
        {"one_time": False, "buttons": [[{"action": {"type": "text", "label": "🔑 Войти по паролю"}, "color": "primary"}]]},
        ensure_ascii=False,
    )


async def find_user_by_vk(vk_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(User).where(User.vk_id == vk_id))


async def _schedule_text(user: User) -> str:
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
                    .limit(7)
                )
            ).all()
        )
    if not events:
        return "Ближайших событий пока нет."
    lines = ["📅 Ближайшие занятия:"]
    for event in events:
        start_at = event.start_datetime.strftime("%d.%m %H:%M")
        place = f" · {event.place}" if event.place else ""
        lines.append(f"• {event.title} — {start_at}{place}")
    return "\n".join(lines)


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

            state = _get_login_state(vk_id)

            # Step 2: awaiting password
            if state and state.get("step") == "awaiting_password":
                ok, msg = await _try_password_link(vk_id, state["telegram_id"], text)
                _vk_login_state.pop(vk_id, None)
                if ok:
                    await message.answer(
                        with_site_link(msg + "\n\nСовет: удалите сообщение с паролем из переписки.", site),
                        keyboard=main_keyboard(),
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
                    await message.answer(with_site_link(result, site), keyboard=main_keyboard())
                return

            await message.answer(link_instructions(settings), keyboard=login_entry_keyboard())
            return
        if "расписан" in low:
            await message.answer(await _schedule_text(user))
        elif "уведомл" in low:
            await message.answer(await _notifications_text(user))
        elif "профиль" in low:
            await message.answer(_profile_text(user))
        else:
            await message.answer(
                with_site_link(
                    f"С возвращением, {user.full_name}! Выберите раздел:",
                    settings.site_url or settings.mini_app_url,
                ),
                keyboard=main_keyboard(),
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
