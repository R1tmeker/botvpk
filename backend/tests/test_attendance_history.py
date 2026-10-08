from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.models import Attendance
from app.routers.attendance import my_attendance


@pytest.mark.asyncio
async def test_history_keeps_old_event_metadata_and_orders_by_class_date():
    start = datetime(2025, 5, 1, 10, tzinfo=timezone.utc)
    row = Attendance(
        id=7, event_id=9, user_id=2, status_code="PRESENT",
        is_draft=False, source_code="COMMANDER",
        marked_at=datetime(2026, 10, 8, 10, tzinfo=timezone.utc),
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        all=lambda: [(row, "Занятие за прошлый год", start)],
    )))
    result = await my_attendance(100, 0, SimpleNamespace(user_id=2), session)
    assert result[0].event_title == "Занятие за прошлый год"
    assert result[0].event_start_datetime == start
    assert result[0].marked_at != start
    query = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert query.params["user_id_1"] == 2
    assert "ORDER BY schedule_events.start_datetime DESC" in str(query)


@pytest.mark.asyncio
async def test_history_tolerates_missing_event_metadata():
    row = Attendance(id=7, event_id=9, user_id=2, status_code="PRESENT", is_draft=False, source_code="SELF")
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(row, None, None)])))
    result = await my_attendance(100, 0, SimpleNamespace(user_id=2), session)
    assert result[0].event_id == 9
    assert result[0].event_title is None
    assert result[0].event_start_datetime is None
