from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import Attendance, AttendanceGrade
from app.services import attendance as service


def event(**overrides):
    values = {
        "id": 11,
        "start_datetime": datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        "self_checkin_enabled": True,
        "self_checkin_opens_at": None,
        "self_checkin_closes_at": None,
        "late_after_minutes": 5,
        "status_code": "PLANNED",
        "grading_type": "NONE",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_self_checkin_updates_unmarked_row_then_is_idempotent() -> None:
    row = Attendance(
        id=3,
        event_id=11,
        user_id=22,
        status_code="NOT_MARKED",
        source_code="SELF",
        is_draft=False,
    )
    session = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock(return_value=row), flush=AsyncMock(), add=Mock())
    now = event().start_datetime

    saved, created = await service.self_check_in(session, event=event(), user_id=22, now=now)
    repeated, repeated_created = await service.self_check_in(session, event=event(), user_id=22, now=now)

    assert saved.status_code == "PRESENT"
    assert created is True
    assert repeated is saved
    assert repeated_created is False
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_self_checkin_refuses_commander_result() -> None:
    row = Attendance(
        id=3,
        event_id=11,
        user_id=22,
        status_code="PRESENT",
        source_code="COMMANDER",
        is_draft=False,
    )
    session = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock(return_value=row))
    with pytest.raises(service.SelfCheckInError, match="commander"):
        await service.self_check_in(session, event=event(), user_id=22, now=event().start_datetime)


@pytest.mark.asyncio
async def test_bulk_attendance_commits_changed_rows_and_skips_identical_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unchanged = Attendance(
        id=1,
        event_id=11,
        user_id=21,
        status_code="PRESENT",
        source_code="COMMANDER",
        is_draft=False,
    )
    changed = Attendance(
        id=2,
        event_id=11,
        user_id=22,
        status_code="NOT_MARKED",
        source_code="SELF",
        is_draft=False,
    )
    result = SimpleNamespace(all=lambda: [unchanged, changed])
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=result),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
        add=Mock(),
    )
    sync = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(service, "sync_automatic_grade", sync)
    monkeypatch.setattr(service, "record_audit", audit)

    saved = await service.bulk_mark_attendance(
        session,
        event=event(),
        actor_id=99,
        changes=[
            service.BulkAttendanceChange(user_id=21, status_code="PRESENT"),
            service.BulkAttendanceChange(user_id=22, status_code="LATE", comment="Опоздал"),
        ],
    )

    assert saved == [unchanged, changed]
    assert changed.status_code == "LATE"
    assert changed.source_code == "COMMANDER"
    sync.assert_awaited_once()
    audit.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_attendance_rolls_back_on_database_error() -> None:
    session = SimpleNamespace(scalars=AsyncMock(side_effect=RuntimeError("db failed")), rollback=AsyncMock())
    with pytest.raises(RuntimeError, match="db failed"):
        await service.bulk_mark_attendance(
            session,
            event=event(),
            actor_id=99,
            changes=[service.BulkAttendanceChange(user_id=21, status_code="PRESENT")],
        )
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_automatic_grade_sets_present_and_clears_absence() -> None:
    attendance = Attendance(id=7, event_id=11, user_id=22, status_code="PRESENT", is_draft=False)
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), add=Mock())
    await service.sync_automatic_grade(session=session, event=event(grading_type="FIVE_POINT"), attendance=attendance, actor_id=9)
    grade = next(call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], AttendanceGrade))
    assert grade.grade_value == "5"

    attendance.status_code = "ABSENT"
    session.scalar.return_value = grade
    await service.sync_automatic_grade(session=session, event=event(grading_type="FIVE_POINT"), attendance=attendance, actor_id=9)
    assert grade.grade_value is None


@pytest.mark.asyncio
async def test_automatic_grade_ignores_non_graded_event() -> None:
    session = SimpleNamespace(scalar=AsyncMock(), add=Mock())
    await service.sync_automatic_grade(
        session=session,
        event=event(grading_type="NONE"),
        attendance=Attendance(id=7, event_id=11, user_id=22, status_code="PRESENT", is_draft=False),
        actor_id=9,
    )
    session.scalar.assert_not_awaited()
