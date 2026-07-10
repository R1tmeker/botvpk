from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..models import NotificationPreference


def channel_enabled(preference: NotificationPreference | None, channel: str) -> bool:
    if preference is None:
        return channel != "web_push"
    return bool(getattr(preference, f"{channel}_enabled"))


def quiet_hours_delivery_time(
    preference: NotificationPreference | None,
    *,
    priority_code: str,
    now: datetime,
    timezone_name: str,
) -> datetime | None:
    if priority_code == "URGENT" or preference is None or not preference.quiet_hours_enabled:
        return None
    if preference.quiet_hours_start is None or preference.quiet_hours_end is None:
        return None
    zone = ZoneInfo(timezone_name)
    now_local = now.astimezone(zone)
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end
    current_time = now_local.timetz().replace(tzinfo=None)
    if start == end:
        in_quiet_hours = True
    elif start < end:
        in_quiet_hours = start <= current_time < end
    else:
        in_quiet_hours = current_time >= start or current_time < end
    if not in_quiet_hours:
        return None
    end_date = now_local.date()
    if start >= end and current_time >= start:
        end_date += timedelta(days=1)
    end_local = datetime.combine(end_date, end, tzinfo=zone)
    return end_local.astimezone(timezone.utc)
