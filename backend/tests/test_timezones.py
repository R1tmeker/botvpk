from __future__ import annotations

from datetime import date, datetime, timezone

from app.utils.timezones import current_local_date, format_club_datetime, local_datetime_to_utc, local_day_utc_bounds, utc_to_local_date


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


def test_barnaul_1600_is_0900_utc_and_never_1300_in_messages() -> None:
    from datetime import time
    instant = local_datetime_to_utc(date(2026, 10, 14), time(16), "Asia/Barnaul")
    assert instant == datetime(2026, 10, 14, 9, tzinfo=timezone.utc)
    assert format_club_datetime(instant, "Asia/Barnaul", "%H:%M") == "16:00"
    assert format_club_datetime(instant.replace(tzinfo=None), "Asia/Barnaul", "%H:%M") == "16:00"
    assert format_club_datetime(datetime(2026, 10, 13, 20, tzinfo=timezone.utc), "Asia/Barnaul") == "14.10.2026 03:00"
