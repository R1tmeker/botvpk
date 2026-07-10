from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.calendar import build_calendar


def test_cancelled_event_keeps_stable_uid_and_cancelled_status() -> None:
    event = SimpleNamespace(
        id=42,
        title="Строевая подготовка",
        description="Описание",
        place="Плац",
        start_datetime=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        end_datetime=None,
        status_code="CANCELLED",
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
    )

    content = build_calendar([event], calendar_name="ВПК Звезда", host="example.test")

    assert "UID:schedule-event-42@example.test" in content
    assert "STATUS:CANCELLED" in content
    assert "SEQUENCE:1" in content
    assert content.endswith("END:VCALENDAR\r\n")
