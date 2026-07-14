from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import User
from app.services.auth_security import (
    PasswordPolicyError,
    bump_token_version,
    password_lockout_state,
    register_failed_password_login,
    register_successful_password_login,
    validate_password_policy,
)
from app.services.totp_secrets import TotpSecretError, decrypt_totp_secret, encrypt_totp_secret


def test_password_policy_rejects_common_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("zvezda123", telegram_id=123456789)


def test_password_policy_requires_letters_and_digits() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("onlyletters", telegram_id=123456789)


def test_password_policy_rejects_short_or_telegram_id_password() -> None:
    with pytest.raises(PasswordPolicyError, match="8 символов"):
        validate_password_policy("A1short")
    with pytest.raises(PasswordPolicyError, match="Telegram ID"):
        validate_password_policy("12345678", telegram_id=12345678)


def test_password_lockout_state_handles_future_lock() -> None:
    user = User(telegram_id=1, full_name="Test", role_code="PARTICIPANT", locked_until=datetime.now(timezone.utc) + timedelta(minutes=5))
    state = password_lockout_state(user)
    assert state.locked is True
    assert state.seconds_left > 0


def test_password_lockout_state_handles_missing_naive_and_expired_values() -> None:
    user = User(telegram_id=1, full_name="Test", role_code="PARTICIPANT", locked_until=None)
    assert password_lockout_state(user).locked is False

    now = datetime.now(timezone.utc)
    user.locked_until = (now + timedelta(seconds=10)).replace(tzinfo=None)
    assert password_lockout_state(user, now=now).locked is True
    user.locked_until = now - timedelta(seconds=1)
    assert password_lockout_state(user, now=now).locked is False


@pytest.mark.asyncio
async def test_failed_password_login_escalates_and_notifies_admin() -> None:
    admin = User(id=50, telegram_id=50, full_name="Admin", role_code="ADMIN", status_code="ACTIVE")
    scalars = SimpleNamespace(all=lambda: [admin])
    session = SimpleNamespace(scalars=AsyncMock(return_value=scalars), add=Mock())
    user = User(
        id=10,
        telegram_id=10,
        full_name="Target",
        role_code="PARTICIPANT",
        failed_login_count=4,
    )

    state = await register_failed_password_login(session, user)

    assert state.locked is True
    assert user.failed_login_count == 5
    assert user.locked_until is not None
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_failed_password_login_below_threshold_does_not_query_admins() -> None:
    session = SimpleNamespace(scalars=AsyncMock(), add=Mock())
    user = User(telegram_id=10, full_name="Target", role_code="PARTICIPANT", failed_login_count=1)

    state = await register_failed_password_login(session, user)

    assert state.locked is False
    assert user.failed_login_count == 2
    session.scalars.assert_not_awaited()


def test_successful_password_login_clears_lockout() -> None:
    user = User(
        telegram_id=1,
        full_name="Test",
        role_code="PARTICIPANT",
        failed_login_count=7,
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    register_successful_password_login(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


def test_bump_token_version_increments_from_none() -> None:
    user = User(telegram_id=1, full_name="Test", role_code="PARTICIPANT", token_version=None)
    bump_token_version(user)
    assert user.token_version == 1


def test_totp_secret_round_trip() -> None:
    key = "a" * 64
    encrypted = encrypt_totp_secret("JBSWY3DPEHPK3PXP", key)
    assert encrypted.startswith("v1:")
    assert "JBSWY3DPEHPK3PXP" not in encrypted
    assert decrypt_totp_secret(encrypted, key) == "JBSWY3DPEHPK3PXP"


def test_totp_secret_fails_closed_with_wrong_key() -> None:
    encrypted = encrypt_totp_secret("JBSWY3DPEHPK3PXP", "a" * 64)
    with pytest.raises(TotpSecretError):
        decrypt_totp_secret(encrypted, "b" * 64)
