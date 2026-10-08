from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import bot, vk_bot
from app.roles import RoleLevel


def test_telegram_id_is_easy_to_find_without_crowding_daily_menu() -> None:
    public = [button.text for row in bot.main_menu_inline(RoleLevel.PUBLIC_USER).inline_keyboard for button in row]
    account = [button.text for row in bot.main_menu_inline(RoleLevel.PARTICIPANT, "account").inline_keyboard for button in row]
    daily = [button.text for row in bot.main_menu_inline(RoleLevel.PARTICIPANT).inline_keyboard for button in row]
    assert "Мой ID" in public
    assert "Мой ID" in account
    assert "Мои данные" in daily
    assert "Мой ID" not in daily


@pytest.mark.asyncio
async def test_my_telegram_id_returns_callers_id(monkeypatch: pytest.MonkeyPatch) -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=123456789), answer=AsyncMock())
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=None))

    await bot.my_telegram_id(message)

    message.answer.assert_awaited_once()
    assert "123456789" in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["parse_mode"] == "HTML"


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
    assert any("отменено" in call.args[0].casefold() for call in message.answer.await_args_list)


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


@pytest.mark.asyncio
async def test_malformed_event_callback_does_not_reach_database(monkeypatch: pytest.MonkeyPatch) -> None:
    find = AsyncMock()
    monkeypatch.setattr(bot, "find_user", find)
    for value in ("event:not-a-number:COMING", "event:1:FORGED", "event:1"):
        callback = SimpleNamespace(data=value, answer=AsyncMock())
        await bot.event_response(callback, AsyncMock())
        callback.answer.assert_awaited_once()
    find.assert_not_awaited()


def test_archived_bot_user_has_no_internal_permissions() -> None:
    assert bot.user_role(SimpleNamespace(role_code="SUPER_ADMIN", status_code="ARCHIVED")) == RoleLevel.PUBLIC_USER


def test_old_bulk_absence_button_is_no_longer_offered() -> None:
    callbacks = [button.callback_data for row in bot.batch_events_keyboard([]).inline_keyboard for button in row]
    assert "batch:COMING" in callbacks
    assert "batch:NOT_COMING" not in callbacks


@pytest.mark.asyncio
async def test_stale_appeal_urgency_does_not_create_an_appeal(monkeypatch):
    state = AsyncMock()
    state.get_state.return_value = None
    database = AsyncMock()
    monkeypatch.setattr(bot, "AsyncSessionLocal", database)
    assert await bot.create_appeal_from_state(SimpleNamespace(), state, "NORMAL", telegram_id=1) is False
    database.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_urgency_callback_is_rejected(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(bot, "create_appeal_from_state", create)
    callback = SimpleNamespace(data="appeal_urgency:FORGED", message=SimpleNamespace(), answer=AsyncMock())
    await bot.appeal_urgency_callback(callback, AsyncMock())
    create.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_appeal_callback_does_not_claim_success(monkeypatch):
    monkeypatch.setattr(bot, "create_appeal_from_state", AsyncMock(return_value=False))
    callback = SimpleNamespace(data="appeal_urgency:NORMAL", message=SimpleNamespace(), from_user=SimpleNamespace(id=7), answer=AsyncMock())
    await bot.appeal_urgency_callback(callback, AsyncMock())
    assert "отправлено" not in callback.answer.await_args.args[0].casefold()


@pytest.mark.asyncio
async def test_reply_rejects_command_instead_of_sending_it(monkeypatch):
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    find = AsyncMock()
    monkeypatch.setattr(bot, "find_user", find)
    message = SimpleNamespace(text="/unrecognised", answer=AsyncMock())
    await bot.appeal_reply_body(message, AsyncMock())
    find.assert_not_awaited()
    assert "не отправлена" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_appeal_thread_button_opens_first_page(monkeypatch):
    user = SimpleNamespace(id=1, status_code="ACTIVE", role_code="PARTICIPANT")
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=user))
    show = AsyncMock()
    monkeypatch.setattr(bot, "send_appeal_thread", show)
    callback = SimpleNamespace(data="appealthread:7:0", message=SimpleNamespace(), from_user=SimpleNamespace(id=11), answer=AsyncMock())
    await bot.appeal_thread_callback(callback, AsyncMock())
    show.assert_awaited_once_with(callback.message, user, 7, 0)


@pytest.mark.asyncio
async def test_back_keeps_application_data_and_returns_to_previous_step(monkeypatch):
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    prompt = AsyncMock()
    monkeypatch.setattr(bot, "prompt_join_step", prompt)
    state = AsyncMock()
    state.get_state.return_value = bot.JoinApplicationStates.motivation.state
    message = SimpleNamespace(answer=AsyncMock())
    await bot.join_back(message, state)
    state.set_state.assert_awaited_once_with(bot.JoinApplicationStates.phone)
    state.clear.assert_not_awaited()
    state.update_data.assert_not_awaited()
    prompt.assert_awaited_once_with(message, state)


@pytest.mark.asyncio
async def test_join_resumes_current_application_without_reset_or_database_lookup(monkeypatch):
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=None))
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    prompt = AsyncMock()
    database = AsyncMock()
    monkeypatch.setattr(bot, "prompt_join_step", prompt)
    monkeypatch.setattr(bot, "AsyncSessionLocal", database)
    state = AsyncMock()
    state.get_state.return_value = bot.JoinApplicationStates.phone.state
    message = SimpleNamespace(from_user=SimpleNamespace(id=7), answer=AsyncMock())
    await bot.join(message, state)
    state.clear.assert_not_awaited()
    database.assert_not_called()
    prompt.assert_awaited_once_with(message, state)


@pytest.mark.asyncio
async def test_join_rejects_another_persons_contact(monkeypatch):
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    state = AsyncMock()
    message = SimpleNamespace(from_user=SimpleNamespace(id=7), contact=SimpleNamespace(user_id=8, phone_number="79991234567"), answer=AsyncMock())
    await bot.join_phone(message, state)
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()
