from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import or_, select

from ..models import Attendance, EventResponse, Notification, ScheduleEvent, User
from ..roles import CONFIRMED_ROLES
from ..utils.audit import utcnow
from ..utils.timezones import local_datetime_to_utc, local_day_utc_bounds, utc_to_local_date


def validate_template(values: dict) -> dict:
    if not values.get("title", "").strip():
        raise ValueError("Укажите название шаблона.")
    try:
        days = sorted({int(item.strip()) for item in values["week_days"].split(",") if item.strip()})
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Выберите дни недели от понедельника до воскресенья.") from exc
    if not days or any(day < 1 or day > 7 for day in days):
        raise ValueError("Выберите хотя бы один день недели.")
    if values.get("start_time") is None:
        raise ValueError("Укажите время начала.")
    if values.get("end_time") and values["end_time"] <= values["start_time"]:
        raise ValueError("Конец занятия должен быть позже начала в тот же день.")
    if values.get("valid_from") and values.get("valid_to") and values["valid_to"] < values["valid_from"]:
        raise ValueError("Дата окончания периода должна быть не раньше даты начала.")
    if values.get("response_deadline_minutes") is not None and not 0 <= values["response_deadline_minutes"] <= 60 * 24 * 30:
        raise ValueError("Срок ответа должен быть от 0 до 43200 минут до занятия.")
    return {**values, "title": values["title"].strip(), "week_days": ",".join(map(str, days))}


def occurrence_dates(template, timezone_name: str, days: int, week_a_start: date | None, now: datetime | None = None) -> list[date]:
    now = now or utcnow()
    today = utc_to_local_date(now, timezone_name)
    if template.week_parity and week_a_start is None:
        raise ValueError("Для недель 1/2 укажите дату начала недели 1 в настройках расписания.")
    weekdays = {int(item) for item in template.week_days.split(",")}
    start = max(template.valid_from or today, today)
    end = min(template.valid_to or today + timedelta(days=days - 1), today + timedelta(days=days - 1))
    result = []
    while start <= end:
        monday = start - timedelta(days=start.weekday())
        parity = "A" if week_a_start and ((monday - week_a_start).days // 7) % 2 == 0 else "B"
        if start.isoweekday() in weekdays and (not template.week_parity or parity == template.week_parity) and local_datetime_to_utc(start, template.start_time, timezone_name) > now:
            result.append(start)
        start += timedelta(days=1)
    return result


async def generate_events(session, template, *, days: int, timezone_name: str, week_a_start: date | None, actor_id: int, sync: bool = False):
    now = utcnow()
    dates = occurrence_dates(template, timezone_name, days, week_a_start, now) if template.is_active else []
    today = utc_to_local_date(now, timezone_name)
    range_start, _ = local_day_utc_bounds(today, timezone_name)
    _, end = local_day_utc_bounds(today + timedelta(days=days - 1), timezone_name)
    existing = list((await session.scalars(select(ScheduleEvent).where(ScheduleEvent.template_id == template.id,
        ScheduleEvent.start_datetime >= range_start, ScheduleEvent.start_datetime < end).order_by(ScheduleEvent.id).with_for_update())).all())
    old_scopes = {item.id: item.squad_id for item in existing}
    by_day = {utc_to_local_date(event.start_datetime, timezone_name): event for event in existing}
    protected = set()
    if sync and existing:
        ids = [item.id for item in existing]
        protected.update((await session.scalars(select(EventResponse.event_id).where(EventResponse.event_id.in_(ids)))).all())
        protected.update((await session.scalars(select(Attendance.event_id).where(Attendance.event_id.in_(ids)))).all())
    created, updated, cancelled, skipped = [], [], [], []
    for day in dates:
        event = by_day.get(day)
        if event is not None and (not sync or event.start_datetime <= now or event.is_overridden or event.id in protected or event.status_code == "CANCELLED"):
            if sync and event.start_datetime > now:
                skipped.append(event)
            continue
        start = local_datetime_to_utc(day, template.start_time, timezone_name)
        values = dict(title=template.title, description=template.description, start_datetime=start,
            end_datetime=local_datetime_to_utc(day, template.end_time, timezone_name) if template.end_time else None,
            place=template.place, squad_id=template.squad_id, requires_response=template.requires_response,
            response_deadline_at=start - timedelta(minutes=template.response_deadline_minutes) if template.response_deadline_minutes is not None else None)
        if event is None:
            event = ScheduleEvent(template_id=template.id, event_type_code="CLASS", created_by_user_id=actor_id, **values)
            session.add(event)
            created.append(event)
        elif any(getattr(event, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(event, key, value)
            event.updated_at = now
            updated.append(event)
    if sync:
        expected = set(dates)
        for event in existing:
            if event.start_datetime <= now or event.status_code == "CANCELLED" or utc_to_local_date(event.start_datetime, timezone_name) in expected:
                continue
            if event.is_overridden or event.id in protected:
                skipped.append(event)
                continue
            event.status_code = "CANCELLED"
            event.updated_at = now
            cancelled.append(event)
    await session.flush()
    await notify_schedule_changes(session, updated, cancelled, old_scopes)
    return created, {"created": len(created), "updated": len(updated), "cancelled": len(cancelled), "preserved": len({item.id for item in skipped})}


async def notify_schedule_changes(session, updated, cancelled, old_scopes=None):
    # Include the original audience if a session has moved to another squad.
    old_scopes = old_scopes or {}
    for event in [*updated, *cancelled]:
        previous_squad = old_scopes.get(event.id, event.squad_id)
        recipients = list((await session.scalars(select(User.id).where(User.status_code == "ACTIVE", User.role_code.in_(CONFIRMED_ROLES),
            or_(event.squad_id is None, previous_squad is None, User.squad_id == event.squad_id, User.squad_id == previous_squad)))).all())
        for user_id in recipients:
            session.add(Notification(user_id=user_id, type_code="SCHEDULE_UPDATE", title="Занятие отменено" if event in cancelled else "Расписание изменилось",
                body=event.title, entity_name="schedule_events", entity_id=event.id, send_to_tg=True))
