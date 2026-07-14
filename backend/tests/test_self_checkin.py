from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.attendance import (
    BulkAttendanceChange,
    SelfCheckInError,
    bulk_mark_attendance,
    ensure_utc,
    resolve_checkin_window,
    self_checkin_status,
)


def event_at(start: datetime, **overrides):
    values = {
        "start_datetime": start,
        "self_checkin_enabled": True,
        "self_checkin_opens_at": None,
        "self_checkin_closes_at": None,
        "late_after_minutes": 5,
        "status_code": "PLANNED",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_default_self_checkin_window_and_late_threshold() -> None:
    start = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    event = event_at(start)

    window = resolve_checkin_window(event)

    assert window.opens_at == start - timedelta(minutes=15)
    assert window.closes_at == start + timedelta(minutes=20)
    assert self_checkin_status(event, start + timedelta(minutes=5)) == "PRESENT"
    assert self_checkin_status(event, start + timedelta(minutes=5, seconds=1)) == "LATE"


@pytest.mark.parametrize(
    ("now_offset", "code"),
    [
        (timedelta(minutes=-16), "not_open"),
        (timedelta(minutes=21), "closed"),
    ],
)
def test_self_checkin_rejects_outside_window(now_offset: timedelta, code: str) -> None:
    start = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(SelfCheckInError) as caught:
        self_checkin_status(event_at(start), start + now_offset)

    assert caught.value.code == code


def test_self_checkin_rejects_disabled_or_cancelled_event() -> None:
    start = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(SelfCheckInError, match="disabled") as disabled:
        self_checkin_status(event_at(start, self_checkin_enabled=False), start)
    with pytest.raises(SelfCheckInError, match="cancelled") as cancelled:
        self_checkin_status(event_at(start, status_code="CANCELLED"), start)

    assert disabled.value.code == "disabled"
    assert cancelled.value.code == "cancelled"


def test_ensure_utc_normalizes_naive_and_aware_values() -> None:
    naive = datetime(2026, 7, 10, 10, 0)
    assert ensure_utc(naive).tzinfo == timezone.utc
    plus_three = naive.replace(tzinfo=timezone(timedelta(hours=3)))
    assert ensure_utc(plus_three) == datetime(2026, 7, 10, 7, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_bulk_attendance_rejects_empty_and_duplicate_batches_before_db_access() -> None:
    session = SimpleNamespace()
    event = SimpleNamespace(id=1)
    with pytest.raises(ValueError, match="No attendance"):
        await bulk_mark_attendance(session, event=event, changes=[], actor_id=1)
    with pytest.raises(ValueError, match="Duplicate"):
        await bulk_mark_attendance(
            session,
            event=event,
            changes=[BulkAttendanceChange(user_id=2, status_code="PRESENT")] * 2,
            actor_id=1,
        )
