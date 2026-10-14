from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from redis.exceptions import ConnectionError

from app import background, vk_bot
from app.services import vk_inbound
from app.services.vk_delivery_policy import suppression_reason
from app.utils.audit import utcnow


@pytest.fixture(autouse=True)
def clear_claims():
    vk_inbound._local_claims.clear()


def message(**kwargs):
    return SimpleNamespace(from_id=42, peer_id=42, text="Меню", payload=None, out=False,
                           answer=AsyncMock(), **kwargs)


async def test_replayed_vk_event_is_only_handled_once_across_concurrent_workers(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: redis)
    handle = AsyncMock()
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    incoming = message(id=0, conversation_message_id=7)
    await asyncio.gather(*(vk_bot.handle_message(incoming) for _ in range(10)))
    handle.assert_awaited_once()
    assert await redis.ttl(vk_inbound.message_key(incoming)) > 86000
    await redis.aclose()


async def test_processing_failure_can_retry_without_duplicating_replies(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: redis)
    attempts = 0
    async def handle(incoming):
        nonlocal attempts
        attempts += 1
        await incoming.answer("Первый ответ")
        if attempts == 1:
            raise RuntimeError("network error")
        await incoming.answer("Второй ответ")
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    incoming = message(id=10)
    with pytest.raises(RuntimeError):
        await vk_bot.handle_message(incoming)
    await vk_bot.handle_message(incoming)
    ids = [call.kwargs["random_id"] for call in incoming.answer.await_args_list]
    assert ids[0] == ids[1] != ids[2]
    assert all(-2_147_483_648 < value < 0 for value in ids)
    await redis.aclose()


async def test_redis_failure_keeps_local_duplicate_protection(monkeypatch):
    redis = SimpleNamespace(set=AsyncMock(side_effect=ConnectionError()))
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: redis)
    handle = AsyncMock()
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    await vk_bot.handle_message(message(id=8))
    await vk_bot.handle_message(message(id=8))
    handle.assert_awaited_once()


async def test_same_text_in_distinct_messages_is_not_dropped(monkeypatch):
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: None)
    handle = AsyncMock()
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    await vk_bot.handle_message(message(id=8))
    await vk_bot.handle_message(message(id=9))
    assert handle.await_count == 2


async def test_bot_never_replies_to_its_own_outgoing_messages(monkeypatch):
    handle = AsyncMock()
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    incoming = message(id=8)
    incoming.out = True
    await vk_bot.handle_message(incoming)
    incoming.out = False
    incoming.from_id = -99
    await vk_bot.handle_message(incoming)
    handle.assert_not_awaited()


async def test_group_chat_does_not_receive_instructions_on_every_message(monkeypatch):
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: None)
    handle = AsyncMock()
    monkeypatch.setattr(vk_bot, "_handle_message", handle)
    incoming = message(id=8)
    incoming.peer_id = 2_000_000_001
    incoming.text = "Обычное сообщение"
    await vk_bot.handle_message(incoming)
    handle.assert_not_awaited()
    incoming.text = "/start"
    await vk_bot.handle_message(incoming)
    incoming.id = 9
    await vk_bot.handle_message(incoming)
    handle.assert_awaited_once()


async def test_expired_schedule_poll_is_preserved_without_sending():
    now = utcnow()
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(status_code="PLANNED", start_datetime=now-timedelta(hours=2), end_datetime=now-timedelta(hours=1))
    incoming = SimpleNamespace(entity_name="schedule_events_2h", entity_id=9, type_code="SCHEDULE_POLL", created_at=now)
    assert await suppression_reason(session, incoming, now) == "event_closed"


async def test_already_answered_member_does_not_receive_another_poll():
    now = utcnow()
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(id=9, status_code="PLANNED", start_datetime=now+timedelta(hours=2), end_datetime=None, response_deadline_at=None)
    session.scalar.return_value = 123
    incoming = SimpleNamespace(entity_name="schedule_events", entity_id=9, user_id=42, type_code="SCHEDULE_POLL", created_at=now)
    assert await suppression_reason(session, incoming, now) == "already_answered"


async def test_announcement_and_appeal_repeated_text_are_preserved():
    session = AsyncMock()
    for code, entity in (("ANNOUNCEMENT", "announcements"), ("APPEAL", "appeals")):
        incoming = SimpleNamespace(type_code=code, entity_name=entity)
        assert await suppression_reason(session, incoming, utcnow()) is None
    session.scalar.assert_not_awaited()


async def test_identical_daily_system_messages_use_creation_window():
    from sqlalchemy.dialects import postgresql
    now = utcnow()
    session = AsyncMock()
    session.scalar.return_value = None
    incoming = SimpleNamespace(id=1, user_id=42, type_code="SYSTEM", entity_name="morning_briefing", entity_id=0, title="Morning", body="No classes", created_at=now)
    assert await suppression_reason(session, incoming, now) is None
    query = session.scalar.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    values = list(compiled.params.values())
    assert now-timedelta(minutes=10) in values
    assert now+timedelta(minutes=10) in values


async def test_sender_defers_retry_and_preserves_inbox_history(monkeypatch):
    now = utcnow()
    incoming = SimpleNamespace(id=7, user_id=42, type_code="ANNOUNCEMENT", category_code="ANNOUNCEMENTS", priority_code="NORMAL", title="Title", body="Body", entity_name="announcements", entity_id=9, deep_link=None)
    session = AsyncMock()
    session.scalar.side_effect = [True, None]
    session.execute.return_value = SimpleNamespace(all=lambda: [(incoming, 42)])
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(background, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(background, "utcnow", lambda: now)
    monkeypatch.setattr(background, "announcement_attachment", AsyncMock(return_value=None))
    send = AsyncMock(side_effect=RuntimeError("network timeout"))
    monkeypatch.setattr(background, "deliver_vk_notification", send)
    settings = SimpleNamespace(vk_bot_enabled=True, vk_group_token="test", site_url=None, mini_app_url=None, timezone="Asia/Barnaul")
    await background.send_pending_vk_notifications(settings)
    assert incoming.vk_retry_after == now+timedelta(minutes=5)
    assert incoming.delivery_error == "network timeout"
    session.commit.assert_awaited_once()


async def test_second_sender_does_not_send_while_database_lock_is_held(monkeypatch):
    session = AsyncMock()
    session.scalar.return_value = False
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(background, "AsyncSessionLocal", lambda: context)
    await background.send_pending_vk_notifications(SimpleNamespace(vk_bot_enabled=True, vk_group_token="test"))
    session.execute.assert_not_awaited()
