from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.roles import RoleLevel
from app.services import appeals


@pytest.mark.asyncio
async def test_inaccessible_appeal_writes_no_message_or_notification():
    session = SimpleNamespace(add=Mock())
    appeal = SimpleNamespace(author_user_id=1)
    with pytest.raises(PermissionError):
        await appeals.add_appeal_reply(session, appeal, sender_id=2, role=RoleLevel.SQUAD_COMMANDER, body="Текст")
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_reply_to_information_request_restores_work_status(monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(appeals, "notify_appeal_commanders", notify)
    monkeypatch.setattr(appeals, "record_audit", AsyncMock())
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    appeal = SimpleNamespace(id=7, author_user_id=1, status_code="NEEDS_INFO", subject="Тема")
    message = await appeals.add_appeal_reply(session, appeal, sender_id=1, role=RoleLevel.PARTICIPANT, body="  Детали  ")
    assert message.body == "Детали"
    assert appeal.status_code == "IN_PROGRESS"
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_appeal_notifications_include_active_admins_and_link_to_conversation():
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [2, 3])), add=Mock())
    appeal = SimpleNamespace(id=7, author_user_id=1, assignee_user_id=2)
    await appeals.notify_appeal_commanders(session, appeal, sender_id=1, title="Новое сообщение", body="Текст")
    statement = session.scalars.await_args.args[0].compile()
    assert "ACTIVE" in statement.params.values()
    assert any(isinstance(value, (set, list, tuple)) and "ADMIN" in value for value in statement.params.values())
    notification = session.add.call_args.args[0]
    assert notification.user_id == 2
    assert notification.category_code == "APPEALS"
    assert notification.deep_link == "/appeals?id=7"
