from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from ..config import get_settings
from ..models import Attendance, EventResponse, Normative, NormativeSubmission, ScheduleEvent, User
from ..roles import role_level
from .event_response_policy import EventResponseError, validate_event_available


def local_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo(get_settings().timezone)).strftime("%d.%m.%Y %H:%M")


def accessible_events(user: User):
    return or_(ScheduleEvent.squad_id.is_(None), ScheduleEvent.squad_id == user.squad_id)


def checkin_statement(user: User, now: datetime, event_id: int | None = None):
    statement = select(ScheduleEvent).where(
        accessible_events(user), ScheduleEvent.status_code != "CANCELLED", ScheduleEvent.self_checkin_enabled.is_(True),
        func.coalesce(ScheduleEvent.self_checkin_opens_at, ScheduleEvent.start_datetime - timedelta(minutes=15)) <= now,
        func.coalesce(ScheduleEvent.self_checkin_closes_at, ScheduleEvent.start_datetime + timedelta(minutes=20)) >= now,
    ).order_by(ScheduleEvent.start_datetime, ScheduleEvent.id)
    return statement.where(ScheduleEvent.id == event_id) if event_id is not None else statement


async def schedule_card(session, user: User, page: int = 0):
    now = datetime.now(timezone.utc)
    events = list((await session.scalars(select(ScheduleEvent).where(
        accessible_events(user), ScheduleEvent.status_code != "CANCELLED",
        or_(func.coalesce(ScheduleEvent.end_datetime, ScheduleEvent.start_datetime) >= now,
            func.coalesce(ScheduleEvent.self_checkin_closes_at, ScheduleEvent.start_datetime + timedelta(minutes=20)) >= now),
    ).order_by(ScheduleEvent.start_datetime, ScheduleEvent.id).offset(page).limit(2))).all())
    if not events:
        return None, "Ближайших занятий пока нет." if page == 0 else "Занятий дальше пока нет. Вернитесь к предыдущему.", False, False
    event = events[0]
    response = await session.scalar(select(EventResponse.response_code).where(EventResponse.user_id == user.id, EventResponse.event_id == event.id))
    try:
        validate_event_available(event, role=role_level(user.role_code), squad_id=user.squad_id, now=now)
        actionable = True
    except EventResponseError:
        actionable = False
    label = {"COMING": "Приду", "NOT_COMING": "Не приду", "MAYBE": "Уточню"}.get(response, "Нет ответа" if event.requires_response else "Не требуется")
    lines = [event.title[:255], local_time(event.start_datetime)]
    if event.place:
        lines.append(f"Место: {event.place[:400]}")
    if event.description:
        lines.append(event.description[:700])
    lines.append(f"Ваш ответ: {label}")
    if actionable:
        if event.response_deadline_at:
            lines.append(f"Ответить до: {local_time(event.response_deadline_at)}")
        lines.append("Ответ о планах не заменяет отметку присутствия.")
    elif event.requires_response:
        lines.append("Приём ответов закрыт.")
    return event, "\n".join(lines), actionable, len(events) > 1


async def attendance_text(session, user: User) -> str:
    rows = (await session.execute(select(Attendance, ScheduleEvent.title, ScheduleEvent.start_datetime)
        .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
        .where(Attendance.user_id == user.id, Attendance.is_draft.is_(False))
        .order_by(ScheduleEvent.start_datetime.desc(), Attendance.id.desc()).limit(10))).all()
    if not rows:
        return "Отметок посещаемости пока нет. Ответ «Приду» в расписании означает только ваши планы."
    labels = {"PRESENT": "Присутствовал", "ABSENT": "Отсутствовал", "LATE": "Опоздал", "EXCUSED": "Уважительная причина", "SICK": "Больничный", "RELEASED": "Освобождён", "NOT_MARKED": "Не отмечен"}
    return "Последние 10 отметок по датам занятий:\n\n" + "\n".join(
        f"• {title[:150]} · {local_time(start)}\n{labels.get(att.status_code, att.status_code)}" for att, title, start in rows)


async def normatives_text(session, user: User, page: int = 0) -> tuple[str, bool]:
    rows = await normative_choices(session, user, page)
    submissions = list((await session.scalars(select(NormativeSubmission).where(NormativeSubmission.user_id == user.id,
        NormativeSubmission.normative_id.in_([item.id for item in rows[:5]]))
        .order_by(NormativeSubmission.submitted_at.desc(), NormativeSubmission.id.desc()))).all()) if rows else []
    latest = {}
    for item in submissions:
        latest.setdefault(item.normative_id, item)
    labels = {"PENDING": "На проверке", "SUBMITTED": "На проверке", "PENDING_REVIEW": "На проверке", "ACCEPTED": "Принят", "REJECTED": "Отклонён", "NEEDS_REDO": "Нужна доработка"}
    lines = [f"Нормативы · страница {page + 1}"]
    for item in rows[:5]:
        submission = latest.get(item.id)
        status = labels.get(submission.status_code, submission.status_code) if submission else "Ещё не сдавали"
        lines.append(f"\n• {item.title[:160]}\nСрок: {local_time(item.deadline_at) if item.deadline_at else 'без срока'}\n{status}")
        if submission and submission.reviewer_comment:
            lines.append(f"Проверяющий: {submission.reviewer_comment[:200]}")
    lines.append("\nДля сдачи пришлите сюда фото, видео или документ, затем выберите норматив." if rows else "Активных нормативов на этой странице нет.")
    return "\n".join(lines), len(rows) > 5


async def normative_choices(session, user: User, page: int = 0, size: int = 5):
    return list((await session.scalars(select(Normative).where(Normative.is_active.is_(True),
        or_(Normative.squad_id.is_(None), Normative.squad_id == user.squad_id))
        .order_by(Normative.deadline_at.nullslast(), Normative.id).offset(page * size).limit(size + 1))).all())
