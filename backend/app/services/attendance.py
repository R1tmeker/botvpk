from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Attendance, AttendanceGrade, AttendanceHistory, ScheduleEvent
from ..utils.audit import record_audit, utcnow


@dataclass(frozen=True, slots=True)
class CheckInWindow:
    opens_at: datetime
    closes_at: datetime
    late_at: datetime


@dataclass(frozen=True, slots=True)
class BulkAttendanceChange:
    user_id: int
    status_code: str
    absence_reason_id: int | None = None
    custom_reason: str | None = None
    comment: str | None = None
    is_draft: bool = False


class SelfCheckInError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_checkin_window(event: ScheduleEvent) -> CheckInWindow:
    start = ensure_utc(event.start_datetime)
    opens_at = ensure_utc(event.self_checkin_opens_at) if event.self_checkin_opens_at else start - timedelta(minutes=15)
    closes_at = (
        ensure_utc(event.self_checkin_closes_at)
        if event.self_checkin_closes_at
        else start + timedelta(minutes=20)
    )
    return CheckInWindow(
        opens_at=opens_at,
        closes_at=closes_at,
        late_at=start + timedelta(minutes=event.late_after_minutes),
    )


def self_checkin_status(event: ScheduleEvent, now: datetime) -> str:
    if not event.self_checkin_enabled:
        raise SelfCheckInError("disabled", "Self check-in is disabled for this event.")
    if event.status_code == "CANCELLED":
        raise SelfCheckInError("cancelled", "The event is cancelled.")
    now_utc = ensure_utc(now)
    window = resolve_checkin_window(event)
    if now_utc < window.opens_at:
        raise SelfCheckInError("not_open", "Self check-in has not opened yet.")
    if now_utc > window.closes_at:
        raise SelfCheckInError("closed", "Self check-in is closed.")
    return "PRESENT" if now_utc <= window.late_at else "LATE"


async def self_check_in(
    session: AsyncSession,
    *,
    event: ScheduleEvent,
    user_id: int,
    now: datetime,
    source_code: str = "SELF",
) -> tuple[Attendance, bool]:
    status_code = self_checkin_status(event, now)
    statement = (
        insert(Attendance)
        .values(
            event_id=event.id,
            user_id=user_id,
            status_code="NOT_MARKED",
            source_code=source_code,
            is_draft=False,
        )
        .on_conflict_do_nothing(index_elements=["event_id", "user_id"])
    )
    await session.execute(statement)
    attendance = await session.scalar(
        select(Attendance)
        .where(Attendance.event_id == event.id, Attendance.user_id == user_id)
        .with_for_update()
    )
    if attendance is None:
        raise RuntimeError("Attendance upsert did not return a row.")
    if attendance.status_code != "NOT_MARKED" or attendance.marked_at is not None:
        if attendance.source_code in {"SELF", "BOT"}:
            return attendance, False
        raise SelfCheckInError("already_marked", "Attendance was already marked by a commander.")

    old_status = attendance.status_code
    old_source = attendance.source_code
    attendance.status_code = status_code
    attendance.absence_reason_id = None
    attendance.custom_reason = None
    attendance.marked_by_user_id = user_id
    attendance.marked_at = ensure_utc(now)
    attendance.updated_at = ensure_utc(now)
    attendance.source_code = source_code
    attendance.is_draft = False
    await session.flush()
    session.add(
        AttendanceHistory(
            attendance_id=attendance.id,
            old_status=old_status,
            new_status=status_code,
            old_source_code=old_source,
            new_source_code=source_code,
            changed_by_id=user_id,
            change_reason="Самоотметка в разрешённое временное окно",
        )
    )
    return attendance, True


async def sync_automatic_grade(
    *,
    session: AsyncSession,
    event: ScheduleEvent,
    attendance: Attendance,
    actor_id: int,
) -> None:
    if event.grading_type != "FIVE_POINT":
        return
    grade = await session.scalar(select(AttendanceGrade).where(AttendanceGrade.attendance_id == attendance.id))
    old_grade = grade.grade_value if grade else None
    if attendance.status_code == "PRESENT":
        if grade is None:
            grade = AttendanceGrade(attendance_id=attendance.id, set_by_user_id=actor_id)
            session.add(grade)
        grade.grade_value = "5"
        grade.comment = grade.comment or "Автоматически за присутствие."
        grade.set_by_user_id = actor_id
        grade.updated_at = utcnow()
    elif attendance.status_code in {"ABSENT", "EXCUSED", "SICK", "RELEASED"} and grade is not None:
        grade.grade_value = None
        grade.updated_at = utcnow()
    if old_grade != (grade.grade_value if grade else None):
        session.add(
            AttendanceHistory(
                attendance_id=attendance.id,
                old_grade=old_grade,
                new_grade=grade.grade_value if grade else None,
                changed_by_id=actor_id,
                change_reason="Автоматическое правило оценивания",
            )
        )


async def bulk_mark_attendance(
    session: AsyncSession,
    *,
    event: ScheduleEvent,
    changes: list[BulkAttendanceChange],
    actor_id: int,
) -> list[Attendance]:
    """Apply a complete commander attendance batch as one transaction."""
    if not changes:
        raise ValueError("No attendance items provided.")
    user_ids = [change.user_id for change in changes]
    if len(user_ids) != len(set(user_ids)):
        raise ValueError("Duplicate user_id in attendance items.")

    try:
        existing = {
            item.user_id: item
            for item in (
                await session.scalars(
                    select(Attendance)
                    .where(Attendance.event_id == event.id, Attendance.user_id.in_(user_ids))
                    .with_for_update()
                )
            ).all()
        }
        saved: list[Attendance] = []
        changed_items: list[dict[str, object]] = []
        now = utcnow()

        for change in changes:
            attendance = existing.get(change.user_id)
            if (
                attendance is not None
                and attendance.status_code == change.status_code
                and attendance.absence_reason_id == change.absence_reason_id
                and attendance.custom_reason == change.custom_reason
                and attendance.is_draft == change.is_draft
                and attendance.source_code == "COMMANDER"
            ):
                saved.append(attendance)
                continue

            old_status = attendance.status_code if attendance else None
            old_source = attendance.source_code if attendance else None
            if attendance is None:
                attendance = Attendance(event_id=event.id, user_id=change.user_id)
                session.add(attendance)
            attendance.status_code = change.status_code
            attendance.absence_reason_id = change.absence_reason_id
            attendance.custom_reason = change.custom_reason
            attendance.marked_by_user_id = actor_id
            attendance.marked_at = now
            attendance.source_code = "COMMANDER"
            attendance.is_draft = change.is_draft
            attendance.updated_at = now
            await session.flush()
            await sync_automatic_grade(session=session, event=event, attendance=attendance, actor_id=actor_id)
            session.add(
                AttendanceHistory(
                    attendance_id=attendance.id,
                    old_status=old_status,
                    new_status=change.status_code,
                    old_source_code=old_source,
                    new_source_code="COMMANDER",
                    changed_by_id=actor_id,
                    change_reason=change.comment,
                )
            )
            saved.append(attendance)
            changed_items.append(
                {
                    "user_id": change.user_id,
                    "status_code": change.status_code,
                    "absence_reason_id": change.absence_reason_id,
                    "custom_reason": change.custom_reason,
                    "comment": change.comment,
                    "is_draft": change.is_draft,
                }
            )

        if changed_items:
            await record_audit(
                session,
                user_id=actor_id,
                action_code="attendance.mark",
                entity_name="schedule_events",
                entity_id=event.id,
                new_value={"items": changed_items},
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    for attendance in saved:
        await session.refresh(attendance)
    return saved
