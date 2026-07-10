from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import ScheduleEvent


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ical_datetime(value: datetime) -> str:
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def _escape(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _fold(line: str) -> list[str]:
    if len(line.encode("utf-8")) <= 75:
        return [line]
    parts: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > (74 if parts else 75):
            parts.append(current)
            current = " " + char
        else:
            current = candidate
    parts.append(current)
    return parts


def build_calendar(events: list[ScheduleEvent], *, calendar_name: str, host: str) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VPK Zvezda//botvpk//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    for item in events:
        end = item.end_datetime or item.start_datetime + timedelta(hours=1)
        updated = item.updated_at or item.created_at or now
        event_lines = [
            "BEGIN:VEVENT",
            f"UID:schedule-event-{item.id}@{host}",
            f"DTSTAMP:{_ical_datetime(updated)}",
            f"DTSTART:{_ical_datetime(item.start_datetime)}",
            f"DTEND:{_ical_datetime(end)}",
            f"SUMMARY:{_escape(item.title)}",
            f"DESCRIPTION:{_escape(item.description)}",
            f"LOCATION:{_escape(item.place)}",
            f"STATUS:{'CANCELLED' if item.status_code == 'CANCELLED' else 'CONFIRMED'}",
            f"SEQUENCE:{1 if item.status_code == 'CANCELLED' or item.updated_at else 0}",
            "END:VEVENT",
        ]
        for line in event_lines:
            lines.extend(_fold(line))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
