from __future__ import annotations

import os
import secrets
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import ScheduleEvent, User
from app.services.attendance import self_check_in
from app.services.sessions import create_auth_session, delete_auth_session, resolve_auth_session
from app.utils.audit import utcnow

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Requires migrated PostgreSQL and a real Redis service.",
)


@pytest.fixture(autouse=True)
async def isolated_database_connections(monkeypatch):
    # pytest gives each async test a new event loop. Do not reuse asyncpg connections across loops.
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    monkeypatch.setitem(globals(), "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_real_redis_opaque_session_roundtrip() -> None:
    settings = get_settings()
    token, _ = await create_auth_session(
        settings,
        user_id=987654321,
        telegram_id=987654321,
        token_version=0,
        step_up=False,
    )
    try:
        resolved = await resolve_auth_session(settings, token)
        assert resolved is not None
        assert resolved.user_id == 987654321
    finally:
        await delete_auth_session(settings, token, user_id=987654321)


@pytest.mark.asyncio
async def test_postgres_self_checkin_is_idempotent_inside_transaction() -> None:
    now = utcnow()
    async with AsyncSessionLocal() as session:
        user = User(
            telegram_id=int(f"99{secrets.randbelow(10**8):08d}"),
            full_name="Integration Test User",
            role_code="PARTICIPANT",
            status_code="ACTIVE",
        )
        session.add(user)
        await session.flush()
        event = ScheduleEvent(
            title="Integration Self Check-in",
            start_datetime=now + timedelta(minutes=1),
            self_checkin_enabled=True,
            created_by_user_id=user.id,
        )
        session.add(event)
        await session.flush()

        first, first_created = await self_check_in(session, event=event, user_id=user.id, now=now)
        second, second_created = await self_check_in(session, event=event, user_id=user.id, now=now)

        assert first.id == second.id
        assert first_created is True
        assert second_created is False
        await session.rollback()


@pytest.mark.asyncio
async def test_announcement_retry_and_telegram_only_delivery_are_idempotent(monkeypatch):
    from uuid import uuid4
    from app.models import Announcement, Notification
    from app.routers.announcements import create_announcement, send_announcement
    from app.schemas.core import AnnouncementCreate
    from app.roles import RoleLevel
    async with AsyncSessionLocal() as session:
        author = User(telegram_id=int(f"97{secrets.randbelow(10**8):08d}"), full_name="Announcement Integration", role_code="SUPER_ADMIN", status_code="ACTIVE")
        session.add(author)
        await session.flush()
        # Endpoint commits become flushes so this test cannot leave delivery jobs behind.
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=session.flush))
        current = SimpleNamespace(user_id=author.id, role_level=RoleLevel.SUPER_ADMIN, squad_id=None)
        payload = AnnouncementCreate(title="Attachment retry", body="Body", send_to_app=False, send_to_tg=True, client_request_id=uuid4())
        first = await create_announcement(payload, current, session)
        await send_announcement(first.id, current, session)
        second = await create_announcement(payload, current, session)
        await send_announcement(second.id, current, session)
        assert first.id == second.id
        assert await session.scalar(select(func.count()).select_from(Announcement).where(Announcement.client_request_id == str(payload.client_request_id))) == 1
        queued = list((await session.scalars(select(Notification).where(Notification.entity_name == "announcements", Notification.entity_id == first.id))).all())
        assert len(queued) >= 1
        assert len({item.user_id for item in queued}) == len(queued)
        assert all(item.send_to_tg and not item.send_to_app for item in queued)
        await session.rollback()


@pytest.mark.asyncio
async def test_template_generation_is_repeatable_and_preserves_responses(monkeypatch):
    from datetime import datetime, time, timezone
    from app.models import EventResponse, ScheduleTemplate
    from app.services import schedule_templates as service
    monkeypatch.setattr(service, "utcnow", lambda: datetime(2026, 10, 12, 1, tzinfo=timezone.utc))
    async with AsyncSessionLocal() as session:
        author = User(telegram_id=int(f"96{secrets.randbelow(10**8):08d}"), full_name="Template Integration", role_code="SUPER_ADMIN", status_code="ACTIVE")
        session.add(author)
        await session.flush()
        item = ScheduleTemplate(title="Template", week_days="1,3", start_time=time(16), requires_response=True, is_active=True, created_by_user_id=author.id)
        session.add(item)
        await session.flush()
        params = dict(days=7, timezone_name="Asia/Barnaul", week_a_start=None, actor_id=author.id)
        first, _ = await service.generate_events(session, item, **params)
        second, _ = await service.generate_events(session, item, **params)
        assert len(first) == 2 and not second
        protected = first[1]
        session.add(EventResponse(event_id=protected.id, user_id=author.id, response_code="COMING"))
        await session.flush()
        item.week_days = "2"
        item.title = "Changed template"
        _, summary = await service.generate_events(session, item, sync=True, **params)
        assert summary == {"created": 1, "updated": 0, "cancelled": 1, "preserved": 1}
        assert protected.title == "Template" and protected.status_code == "PLANNED"
        assert first[0].status_code == "CANCELLED"
        item.week_days = "1"
        recreated, _ = await service.generate_events(session, item, **params)
        assert not recreated  # A manually cancelled date must never be resurrected by generation.
        await session.rollback()


@pytest.mark.asyncio
async def test_bot_queries_include_custom_checkin_windows_and_current_events() -> None:
    from app.services.bot_content import checkin_statement, schedule_card
    now = utcnow()
    async with AsyncSessionLocal() as session:
        user = User(telegram_id=int(f"98{secrets.randbelow(10**8):08d}"), full_name="Bot Flow Integration", role_code="PARTICIPANT", status_code="ACTIVE")
        session.add(user)
        await session.flush()
        event = ScheduleEvent(title="Custom window", start_datetime=now - timedelta(hours=4), end_datetime=now + timedelta(hours=1),
            self_checkin_enabled=True, self_checkin_opens_at=now - timedelta(hours=5), self_checkin_closes_at=now + timedelta(minutes=10), created_by_user_id=user.id)
        session.add(event)
        await session.flush()
        matches = list((await session.scalars(checkin_statement(user, now, event.id))).all())
        assert [item.id for item in matches] == [event.id]
        # Every card query must execute against PostgreSQL's timestamp/interval types.
        card, text, actionable, _ = await schedule_card(session, user)
        assert card is not None
        if card.id == event.id:
            assert "Custom window" in text
            assert not actionable
        await session.rollback()
