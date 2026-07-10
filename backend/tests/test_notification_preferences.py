from datetime import datetime, time, timezone
from types import SimpleNamespace

from app.services.notifications import quiet_hours_delivery_time


def preference(start: time, end: time):
    return SimpleNamespace(
        quiet_hours_enabled=True,
        quiet_hours_start=start,
        quiet_hours_end=end,
    )


def test_overnight_quiet_hours_defer_until_local_end() -> None:
    now = datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)  # 01:00 in Novosibirsk

    delivery_time = quiet_hours_delivery_time(
        preference(time(23, 0), time(7, 0)),
        priority_code="NORMAL",
        now=now,
        timezone_name="Asia/Novosibirsk",
    )

    assert delivery_time == datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)


def test_urgent_notification_bypasses_quiet_hours() -> None:
    now = datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)

    assert quiet_hours_delivery_time(
        preference(time(23, 0), time(7, 0)),
        priority_code="URGENT",
        now=now,
        timezone_name="Asia/Novosibirsk",
    ) is None
