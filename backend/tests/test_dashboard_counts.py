from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import EventResponse, ScheduleEvent, User
from app.roles import RoleLevel
from app.routers import dashboard
from app.services.action_center import pending_event_responses


@pytest.mark.asyncio
async def test_pending_pairs_exclude_archived_people_and_ineligible_events():
    engine = create_engine("sqlite://")
    for table in (User.__table__, ScheduleEvent.__table__, EventResponse.__table__):
        table.create(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add_all([User(id=i, full_name=f"User {i}", telegram_id=990000000+i, squad_id=1 if i<3 else 2,
                         role_code="PUBLIC_USER" if i==5 else "PARTICIPANT", status_code="ARCHIVED" if i==4 else "ACTIVE") for i in range(1, 6)])
        for i in range(1, 8):
            db.add(ScheduleEvent(id=i, title=f"Event {i}", start_datetime=now+timedelta(hours=i*4) if i<6 else now+timedelta(days=2) if i==6 else now-timedelta(days=1),
                                 squad_id=2 if i==3 else None, created_by_user_id=1,
                                 requires_response=i!=5, status_code="CANCELLED" if i==4 else "PLANNED",
                                 response_deadline_at=now-timedelta(minutes=1) if i==6 else None))
        db.add_all([EventResponse(event_id=1, user_id=1, response_code="COMING"), EventResponse(event_id=2, user_id=1, response_code="MAYBE")])
        db.commit()
        class ReadSession:
            async def scalars(self, query): return db.scalars(query)
            async def execute(self, query): return db.execute(query)
        pending = await pending_event_responses(ReadSession(), now=now, scoped_squad_id=None)
        assert {event.id: users for event, users in pending} == {1: {2, 3}, 2: {1, 2, 3}, 3: {3}}
        assert len(set().union(*(users for _, users in pending))) == 3
        assert sum(len(users) for _, users in pending) == 6
        scoped = await pending_event_responses(ReadSession(), now=now, scoped_squad_id=1)
        assert {event.id: users for event, users in scoped} == {1: {2}, 2: {1, 2}}
    engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_counts_people_once_across_multiple_classes(monkeypatch):
    event = SimpleNamespace(response_deadline_at=None)
    monkeypatch.setattr(dashboard, "pending_event_responses", AsyncMock(return_value=[(event, {1, 2}), (event, {1, 2, 3})]))
    db = AsyncMock()
    db.scalar.return_value = 0
    db.scalars.return_value = SimpleNamespace(all=lambda: [])
    items = await dashboard.dashboard_action_items(SimpleNamespace(role_level=RoleLevel.SUPER_ADMIN, squad_id=None), db)
    assert len(items) == 1
    assert items[0].count == 3
    assert "Открытых голосований: 2" in items[0].description
    assert "ожидается ответов: 5" in items[0].description
