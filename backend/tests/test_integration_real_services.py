from __future__ import annotations

import os
import secrets
from datetime import timedelta

import pytest

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
