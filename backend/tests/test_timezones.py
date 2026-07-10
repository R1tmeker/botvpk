from __future__ import annotations

from datetime import date, datetime, timezone

from app.utils.timezones import current_local_date, local_day_utc_bounds, utc_to_local_date


def test_novosibirsk_day_bounds_are_converted_to_utc() -> None:
    start, end = local_day_utc_bounds(date(2026, 7, 10), "Asia/Novosibirsk")
    assert start == datetime(2026, 7, 9, 17, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 10, 17, 0, tzinfo=timezone.utc)


def test_current_local_date_handles_utc_midnight_boundary() -> None:
    now = datetime(2026, 7, 9, 18, 30, tzinfo=timezone.utc)
    assert current_local_date("Asia/Novosibirsk", now=now) == date(2026, 7, 10)


def test_utc_event_maps_to_local_date() -> None:
    event_time = datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc)
    assert utc_to_local_date(event_time, "Asia/Novosibirsk") == date(2026, 7, 10)
