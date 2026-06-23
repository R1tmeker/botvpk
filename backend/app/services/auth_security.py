from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification, User

LOGIN_LOCKOUT_THRESHOLD = 5
LOGIN_LOCKOUT_BASE_MINUTES = 15
LOGIN_LOCKOUT_MAX_MINUTES = 24 * 60

COMMON_PASSWORDS = {
    "password",
    "password1",
    "qwerty123",
    "12345678",
    "123456789",
    "11111111",
    "87654321",
    "admin123",
    "letmein1",
    "vpkzvezda",
    "zvezda123",
}


class PasswordPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class LockoutState:
    locked: bool
    seconds_left: int = 0


def validate_password_policy(password: str, *, telegram_id: int | None = None) -> None:
    value = password.strip()
    lowered = value.casefold()
    if len(value) < 8:
        raise PasswordPolicyError("Пароль должен быть не короче 8 символов.")
    if value.isdigit():
        raise PasswordPolicyError("Пароль не должен состоять только из цифр.")
    if telegram_id is not None and value == str(telegram_id):
        raise PasswordPolicyError("Пароль не должен совпадать с Telegram ID.")
    if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
        raise PasswordPolicyError("Пароль должен содержать хотя бы одну букву и одну цифру.")
    if lowered in COMMON_PASSWORDS:
        raise PasswordPolicyError("Пароль слишком распространённый. Выберите другой.")


def password_lockout_state(user: User, *, now: datetime | None = None) -> LockoutState:
    now = now or datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until is None:
        return LockoutState(False)
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until <= now:
        return LockoutState(False)
    return LockoutState(True, max(1, int((locked_until - now).total_seconds())))


async def register_failed_password_login(session: AsyncSession, user: User) -> LockoutState:
    failures = (user.failed_login_count or 0) + 1
    user.failed_login_count = failures
    if failures < LOGIN_LOCKOUT_THRESHOLD:
        return LockoutState(False)

    extra_failures = failures - LOGIN_LOCKOUT_THRESHOLD
    lock_minutes = min(
        LOGIN_LOCKOUT_BASE_MINUTES * (2 ** max(extra_failures, 0)),
        LOGIN_LOCKOUT_MAX_MINUTES,
    )
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)
    await notify_admins_about_password_lockout(session, user, failures=failures, lock_minutes=lock_minutes)
    return password_lockout_state(user)


def register_successful_password_login(user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None


def bump_token_version(user: User) -> None:
    user.token_version = (user.token_version or 0) + 1


async def notify_admins_about_password_lockout(
    session: AsyncSession,
    user: User,
    *,
    failures: int,
    lock_minutes: int,
) -> None:
    admins = list(
        (
            await session.scalars(
                select(User).where(
                    User.status_code == "ACTIVE",
                    User.role_code.in_(("ADMIN", "SUPER_ADMIN", "PLATOON_COMMANDER")),
                )
            )
        ).all()
    )
    if not admins:
        return
    title = "Заблокирован вход по паролю"
    body = (
        f"Аккаунт {user.full_name} (Telegram ID {user.telegram_id}) временно заблокирован "
        f"после {failures} неудачных попыток. Блокировка: {lock_minutes} мин."
    )
    for admin in admins:
        session.add(
            Notification(
                user_id=admin.id,
                type_code="URGENT",
                title=title,
                body=body,
                entity_name="users",
                entity_id=user.id,
                send_to_tg=True,
            )
        )
