from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import User
from app.services.auth_security import (
    PasswordPolicyError,
    bump_token_version,
    password_lockout_state,
    register_successful_password_login,
    validate_password_policy,
)


def test_password_policy_rejects_common_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("zvezda123", telegram_id=123456789)


def test_password_policy_requires_letters_and_digits() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("onlyletters", telegram_id=123456789)


def test_password_lockout_state_handles_future_lock() -> None:
    user = User(telegram_id=1, full_name="Test", role_code="PARTICIPANT", locked_until=datetime.now(timezone.utc) + timedelta(minutes=5))
    state = password_lockout_state(user)
    assert state.locked is True
    assert state.seconds_left > 0


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
