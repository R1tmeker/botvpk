from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.roles import RoleLevel
from app.routers import schedule
from app.schemas.core import BulkEventResponseCreate
from app.services import notification_inbox, search


def actor(role=RoleLevel.PARTICIPANT):
    return SimpleNamespace(user_id=1, squad_id=1, role_level=role)


def event(event_id=1, **overrides):
    now = datetime.now(timezone.utc)
    values = dict(id=event_id, squad_id=1, requires_response=True, status_code="PLANNED",
                  start_datetime=now + timedelta(days=1), response_deadline_at=now + timedelta(hours=1))
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_invalid_bulk_selection_writes_no_answers(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(schedule, "respond_to_event", save)
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [event(), event(2, squad_id=2)])), rollback=AsyncMock(), commit=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await schedule.respond_events_bulk(BulkEventResponseCreate(event_ids=[1, 2]), actor(), session)
    assert exc.value.status_code == 403
    save.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_commit_happens_once_and_preserves_requested_ids(monkeypatch):
    save, audit, publish = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(schedule, "respond_to_event", save)
    monkeypatch.setattr(schedule, "record_audit", audit)
    monkeypatch.setattr(schedule, "publish_response_update", publish)
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [event(), event(2)])), rollback=AsyncMock(), commit=AsyncMock())
    result = await schedule.respond_events_bulk(BulkEventResponseCreate(event_ids=[2, 1]), actor(), session)
    assert result.event_ids == [2, 1]
    assert result.count == 2
    assert save.await_count == 2
    session.commit.assert_awaited_once()
    publish.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_missing_bulk_event_is_rejected_before_writing(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(schedule, "respond_to_event", save)
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [event()])))
    with pytest.raises(HTTPException) as exc:
        await schedule.respond_events_bulk(BulkEventResponseCreate(event_ids=[1, 2]), actor(), session)
    assert exc.value.status_code == 404
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_read_is_owner_scoped_and_idempotent():
    previous = datetime(2026, 10, 1, tzinfo=timezone.utc)
    row = SimpleNamespace(is_read=True, read_at=previous)
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    assert await notification_inbox.mark_notification_read(session, 42, 7) is row
    statement = session.scalar.await_args.args[0].compile()
    assert 42 in statement.params.values() and 7 in statement.params.values()
    assert row.read_at == previous
    session.scalar.return_value = None
    assert await notification_inbox.mark_notification_read(session, 42, 8) is None


@pytest.mark.asyncio
async def test_notification_search_escapes_wildcards_and_pages_with_stable_order():
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await notification_inbox.inbox_page(session, 42, query="100%_", unread_only=True, limit=21, offset=20)
    statement = session.scalars.await_args.args[0].compile()
    assert "%100\\%\\_%" in statement.params.values()
    assert 42 in statement.params.values() and 20 in statement.params.values()
    assert "notifications.id DESC" in str(statement)


@pytest.mark.asyncio
async def test_search_uses_material_and_appeal_visibility_rules():
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await search.search_accessible(session, "тренировка", role=RoleLevel.SQUAD_COMMANDER,
                                   role_code="SQUAD_COMMANDER", squad_id=1, user_id=42)
    material_sql = session.scalars.await_args_list[2].args[0].compile()
    appeal_sql = session.scalars.await_args_list[3].args[0].compile()
    assert "learning_materials.audience_code IN" in str(material_sql)
    assert "appeals.author_user_id" in str(appeal_sql)
    assert 42 in appeal_sql.params.values()


@pytest.mark.asyncio
async def test_short_search_does_not_query_database():
    session = SimpleNamespace(scalars=AsyncMock())
    assert await search.search_accessible(session, "  ", role=RoleLevel.PARTICIPANT, role_code="PARTICIPANT", squad_id=1, user_id=1) == []
    session.scalars.assert_not_awaited()
