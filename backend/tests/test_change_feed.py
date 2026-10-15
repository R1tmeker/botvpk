import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Notification, User
from app.services import realtime
from app.services.change_feed import install_change_feed
from app.services.join_notifications import notify_new_application
from test_normative_cycles import AsyncAdapter


@pytest.mark.asyncio
async def test_changes_publish_only_after_commit_and_refresh_roles(monkeypatch):
    publish = AsyncMock()
    monkeypatch.setattr(realtime, "publish_realtime_event", publish)
    install_change_feed()
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with Session(engine) as db:
        user = User(full_name="User", telegram_id=123, role_code="PARTICIPANT", status_code="ACTIVE")
        db.add(user)
        db.flush()
        publish.assert_not_awaited()
        db.commit()
        await asyncio.sleep(0)
        assert publish.await_count == 1
        assert {"me", "users", "admin", "normatives"} <= set(publish.await_args.kwargs["query_keys"])
        publish.reset_mock()
        user.role_code = "ADMIN"
        db.flush()
        db.rollback()
        await asyncio.sleep(0)
        publish.assert_not_awaited()
        with db.begin_nested():
            user.status_code = "ARCHIVED"
            db.flush()
        await asyncio.sleep(0)
        publish.assert_not_awaited()
        db.commit()
        await asyncio.sleep(0)
        publish.assert_awaited_once()
    engine.dispose()


@pytest.mark.asyncio
async def test_new_application_reaches_admins_once_and_skips_inactive_reviewers():
    engine = create_engine("sqlite://")
    for model in (User, Notification):
        model.__table__.create(engine)
    with Session(engine) as db:
        for index, role in enumerate(
            ["ADMIN", "SUPER_ADMIN", "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "SQUAD_COMMANDER", "ADMIN"], 1
        ):
            db.add(
                User(
                    id=index,
                    full_name=role,
                    telegram_id=index,
                    role_code=role,
                    status_code="ARCHIVED" if index == 6 else "ACTIVE",
                )
            )
        db.flush()
        session = AsyncAdapter(db)
        application = SimpleNamespace(id=22, full_name="Новый кандидат")
        assert await notify_new_application(session, application) == 4
        assert await notify_new_application(session, application) == 0
        notices = db.scalars(select(Notification)).all()
        assert {item.user_id for item in notices} == {1, 2, 3, 4}
        assert all(item.send_to_tg and item.send_to_app and item.priority_code == "URGENT" for item in notices)
        assert all("application=22" in item.deep_link for item in notices)
    engine.dispose()


@pytest.mark.parametrize("level", [0, 1, 2, 3, 9])
@pytest.mark.asyncio
async def test_authenticated_candidates_also_receive_status_updates(monkeypatch, level):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_db_session
    from app.dependencies.auth import get_current_user
    from app.routers import events

    session = AsyncMock()

    async def database_session():
        yield session

    async def fake_stream(*args, **kwargs):
        session.close.assert_awaited_once()
        yield 'event: connected\ndata: {"type":"connected"}\n\n'

    monkeypatch.setattr(events, "event_stream", fake_stream)
    app = FastAPI()
    app.include_router(events.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=7, role_level=level)
    app.dependency_overrides[get_db_session] = database_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/events/stream")
        assert response.status_code == 200
        assert "event: connected" in response.text
        app.dependency_overrides.clear()
        response = await client.get("/events/stream")
        assert response.status_code == 401
