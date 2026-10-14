from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_club_datetime(value: datetime, timezone_name: str, pattern: str = "%d.%m.%Y %H:%M") -> str:
    """Database timestamps are UTC; never infer the host's local timezone."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name)).strftime(pattern)


def club_timezone_label(timezone_name: str) -> str:
    return {"Asia/Barnaul": "Барнаул (МСК+4)", "Asia/Novosibirsk": "Новосибирск (МСК+4)"}.get(timezone_name, timezone_name)


def current_local_date(timezone_name: str, *, now: datetime | None = None) -> date:
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(ZoneInfo(timezone_name)).date()


def local_datetime_to_utc(value_date: date, value_time: time, timezone_name: str) -> datetime:
    local = datetime.combine(value_date, value_time, tzinfo=ZoneInfo(timezone_name))
    return local.astimezone(timezone.utc)


def local_day_utc_bounds(value: date, timezone_name: str) -> tuple[datetime, datetime]:
    start = local_datetime_to_utc(value, time.min, timezone_name)
    next_day = local_datetime_to_utc(value + timedelta(days=1), time.min, timezone_name)
    return start, next_day


def utc_to_local_date(value: datetime, timezone_name: str) -> date:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name)).date()
