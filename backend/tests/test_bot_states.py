from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import bot, vk_bot


@pytest.mark.asyncio
async def test_telegram_dialog_timeout_clears_state_and_notifies_user() -> None:
    state = AsyncMock()
    state.get_data.return_value = {
        "started_at": (datetime.now(timezone.utc) - bot.JOIN_STATE_TIMEOUT - timedelta(seconds=1)).isoformat()
    }
    message = SimpleNamespace(answer=AsyncMock())

    assert await bot.ensure_dialog_not_expired(message, state) is True
    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_cancel_clears_any_fsm_state(monkeypatch: pytest.MonkeyPatch) -> None:
    state = AsyncMock()
    state.get_state.return_value = "appeal:description"
    message = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=None))

    await bot.cancel_dialog(message, state)

    state.clear.assert_awaited_once()
    assert "отменено" in message.answer.await_args.args[0].casefold()


@pytest.mark.asyncio
async def test_vk_dialog_state_has_ttl_and_can_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: None)
    vk_bot._vk_login_state.clear()

    await vk_bot._set_login_state(42, step="awaiting_password", telegram_id=7)
    current = await vk_bot._get_login_state(42)
    assert current is not None
    assert current["step"] == "awaiting_password"
    assert current["telegram_id"] == 7

    vk_bot._vk_login_state[42]["ts"] = datetime.now(timezone.utc) - timedelta(
        seconds=vk_bot._LOGIN_STATE_TTL_SECONDS + 1
    )
    assert await vk_bot._get_login_state(42) is None

    await vk_bot._set_login_state(42, step="awaiting_login")
    await vk_bot._clear_login_state(42)
    assert await vk_bot._get_login_state(42) is None
