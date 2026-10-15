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
async def test_automatic_absence_waits_for_the_end_of_class(monkeypatch):
    from app import background
    from app.models import Attendance, EventResponse
    now = utcnow()
    async with AsyncSessionLocal() as session:
        user = User(telegram_id=int(f"96{secrets.randbelow(10**8):08d}"), full_name="Absence Integration", role_code="PARTICIPANT", status_code="ACTIVE")
        session.add(user)
        await session.flush()
        event = ScheduleEvent(title="Ongoing class", start_datetime=now-timedelta(minutes=5), end_datetime=now+timedelta(hours=1), created_by_user_id=user.id)
        session.add(event)
        await session.flush()
        session.add(EventResponse(event_id=event.id, user_id=user.id, response_code="NOT_COMING"))
        await session.flush()
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=session.flush))
        context = AsyncMock()
        context.__aenter__.return_value = session
        monkeypatch.setattr(background, "AsyncSessionLocal", lambda:context)
        monkeypatch.setattr(background, "utcnow", lambda:now)
        await background.materialize_absent_responses()
        query = select(Attendance).where(Attendance.event_id==event.id, Attendance.user_id==user.id)
        assert await session.scalar(query) is None
        monkeypatch.setattr(background, "utcnow", lambda:now+timedelta(days=2))
        await background.materialize_absent_responses()
        assert (await session.scalar(query)).status_code == "ABSENT"
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
            assert actionable
        await session.rollback()


@pytest.mark.asyncio
async def test_vk_queue_paces_recipients_preserves_files_and_suppresses_duplicates(monkeypatch):
    from app import background
    from app.models import Notification
    from app.services.vk_delivery_policy import pending_vk_statement
    now = utcnow()
    async with AsyncSessionLocal() as session:
        users = [User(telegram_id=int(f"95{secrets.randbelow(10**8):08d}"), vk_id=int(f"95{secrets.randbelow(10**8):08d}"), full_name="VK Delivery Integration", role_code="PARTICIPANT", status_code="ACTIVE") for _ in range(2)]
        session.add_all(users)
        await session.flush()
        items = [Notification(user_id=user.id, type_code="SYSTEM", entity_name="integration_antispam", entity_id=1, title="Same automated message", body="Body", created_at=now-timedelta(minutes=2), send_to_tg=True) for user in users for _ in range(3)]
        session.add_all(items)
        await session.flush()
        settings = SimpleNamespace(vk_bot_enabled=True, vk_group_token="test", site_url=None, mini_app_url=None, timezone="Asia/Barnaul")
        context = AsyncMock()
        context.__aenter__.return_value = session
        monkeypatch.setattr(background, "AsyncSessionLocal", lambda: context)
        monkeypatch.setattr(background, "utcnow", lambda: now)
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=session.flush))
        send = AsyncMock()
        monkeypatch.setattr(background, "deliver_vk_notification", send)
        monkeypatch.setattr(background, "vk_rate_limit_pause", AsyncMock())
        await background.send_pending_vk_notifications(settings)
        assert send.await_count == 2  # One per recipient, despite six queued items.
        assert not (await session.execute(pending_vk_statement(now))).all()
        monkeypatch.setattr(background, "utcnow", lambda: now+timedelta(minutes=2))
        await background.send_pending_vk_notifications(settings)
        assert send.await_count == 2  # Exact automated repeats remain in inbox only.
        assert sum(item.vk_suppressed_at is not None for item in items) == 2
        assert await session.scalar(select(func.count(Notification.id)).where(Notification.id.in_([item.id for item in items]))) == 6
        await session.rollback()


@pytest.mark.asyncio
async def test_mass_reminder_is_one_digest_per_member_and_repeat_click_is_safe(monkeypatch):
    from app.models import Notification
    from app.services import action_center
    now = utcnow()
    async with AsyncSessionLocal() as session:
        user = User(telegram_id=int(f"94{secrets.randbelow(10**8):08d}"), full_name="Reminder Integration", role_code="PARTICIPANT", status_code="ACTIVE")
        session.add(user)
        await session.flush()
        events = [ScheduleEvent(title=f"Class {index}", start_datetime=now+timedelta(days=index+1), created_by_user_id=user.id) for index in range(4)]
        session.add_all(events)
        await session.flush()
        monkeypatch.setattr(action_center, "pending_event_responses", AsyncMock(return_value=[(event, {user.id}) for event in events]))
        assert await action_center._send_response_reminders(session, now=now, scoped_squad_id=None) == 1
        await session.flush()
        assert await action_center._send_response_reminders(session, now=now, scoped_squad_id=None) == 0
        queued = list((await session.scalars(select(Notification).where(Notification.user_id==user.id))).all())
        assert len(queued) == 1 and all(event.title in queued[0].body for event in events)
        assert queued[0].deep_link == "/schedule"
        await session.rollback()


@pytest.mark.asyncio
async def test_postgres_weekly_normative_history_and_repeated_submission(monkeypatch):
    from datetime import date, datetime, timezone
    from app.models import Normative, NormativeSubmission
    from app.services import normatives

    now = datetime(2026, 10, 11, 16, 59, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(normatives, "utcnow", lambda: now)
    monkeypatch.setattr(normatives, "_commander_recipients", AsyncMock(return_value=[]))
    async with AsyncSessionLocal() as session:
        user = User(telegram_id=int(f"93{secrets.randbelow(10**8):08d}"), full_name="Weekly Cycle Integration", role_code="PARTICIPANT", status_code="ACTIVE")
        session.add(user)
        await session.flush()
        normative = Normative(title="Weekly integration", type_code="GENERAL", recurrence_days=7, recurrence_start_date=date(2026, 10, 5), created_by_user_id=user.id)
        session.add(normative)
        await session.flush()
        args = dict(normative=normative, submitter=user, status_code="SUBMITTED", comment="First week", file_ids=[], audit_action_code="test.weekly", audit_value={})
        first = await normatives.submit_normative(session, **args)
        first.status_code = "ACCEPTED"
        await session.flush()
        assert await normatives.submit_normative(session, **args) is first
        now += timedelta(seconds=1)
        second = await normatives.submit_normative(session, **args)
        await session.flush()
        assert second.id != first.id
        assert first.status_code == "ACCEPTED"
        assert first.period_start_date == date(2026, 10, 5)
        assert second.period_start_date == date(2026, 10, 12)
        assert len((await session.scalars(select(NormativeSubmission).where(NormativeSubmission.normative_id == normative.id))).all()) == 2
        await session.rollback()
