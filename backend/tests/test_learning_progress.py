from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.roles import RoleLevel
from app.routers import learning
from app.routers.admin import learning as admin_learning


def actor(user_id=42):
    return SimpleNamespace(user_id=user_id, role_code="PARTICIPANT", role_level=RoleLevel.PARTICIPANT)


def material(**overrides):
    return SimpleNamespace(**{"id": 7, "title": "Первая помощь", "type_code": "TEXT", "audience_code": "PARTICIPANTS",
        "sort_order": 0, "is_active": True, "created_at": datetime.now(timezone.utc), **overrides})


def result(values):
    return SimpleNamespace(all=lambda: values)


@pytest.mark.asyncio
async def test_learning_progress_is_scoped_to_the_current_profile():
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(scalars=AsyncMock(side_effect=[result([material()]), result([SimpleNamespace(material_id=7, viewed_at=now)])]))
    items = await learning.learning_materials(None, actor(), session)
    assert items[0].is_viewed is True and items[0].viewed_at == now
    query = session.scalars.await_args_list[1].args[0].compile()
    assert "learning_progress.user_id =" in str(query) and 42 in query.params.values()


@pytest.mark.asyncio
async def test_missing_profile_never_loads_anyone_else_progress():
    session = SimpleNamespace(scalars=AsyncMock(return_value=result([material()])))
    items = await learning.learning_materials(None, actor(None), session)
    assert items[0].is_viewed is False and items[0].viewed_at is None
    assert session.scalars.await_count == 1


@pytest.mark.asyncio
async def test_mark_viewed_uses_idempotent_insert_and_current_user_key():
    session = SimpleNamespace(get=AsyncMock(return_value=material()), execute=AsyncMock(), commit=AsyncMock())
    await learning.mark_material_viewed(7, actor(), session)
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (user_id, material_id) DO NOTHING" in str(query)
    assert query.params["user_id"] == 42 and query.params["material_id"] == 7
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_progress_deletes_only_the_current_users_mark():
    session = SimpleNamespace(get=AsyncMock(return_value=material()), execute=AsyncMock(), commit=AsyncMock())
    await learning.reset_material_viewed(7, actor(), session)
    query = session.execute.await_args.args[0].compile()
    assert "learning_progress.user_id =" in str(query) and set(query.params.values()) == {42, 7}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("item", [None, material(is_active=False), material(audience_code="ADMIN")])
async def test_hidden_material_cannot_be_marked_or_reset(item):
    for action in (learning.mark_material_viewed, learning.reset_material_viewed):
        session = SimpleNamespace(get=AsyncMock(return_value=item), execute=AsyncMock(), commit=AsyncMock())
        with pytest.raises(HTTPException) as exc:
            await action(7, actor(), session)
        assert exc.value.status_code == 404
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_lists_include_hidden_content_and_can_filter_active_content():
    for action in (admin_learning.list_admin_materials, admin_learning.list_admin_courses):
        session = SimpleNamespace(scalars=AsyncMock(return_value=result([])))
        await action(False, actor(), session)
        assert "WHERE" not in str(session.scalars.await_args.args[0].compile())
        await action(True, actor(), session)
        assert "is_active IS true" in str(session.scalars.await_args.args[0].compile())


@pytest.mark.asyncio
async def test_missing_course_is_a_validation_error_instead_of_a_database_error():
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await admin_learning.validate_course(session, 999)
    assert exc.value.status_code == 422
