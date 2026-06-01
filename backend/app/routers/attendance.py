from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import Attendance, AttendanceGrade, AttendanceHistory, ScheduleEvent, User
from ..roles import RoleLevel
from ..schemas.core import (
    AttendanceGradeRead,
    AttendanceGradeUpdate,
    AttendanceMarkRequest,
    AttendanceRead,
    AttendanceUpdate,
    MessageResponse,
    ReportSummary,
)
from ..utils.audit import model_snapshot, record_audit, utcnow

router = APIRouter(prefix="/attendance", tags=["attendance"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


async def get_event_or_404(session: AsyncSession, event_id: int) -> ScheduleEvent:
    event = await session.get(ScheduleEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return event


async def ensure_can_manage_attendance(
    *,
    session: AsyncSession,
    current_user: CurrentUser,
    event: ScheduleEvent,
    user_ids: list[int],
) -> None:
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        return
    if current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER or current_user.squad_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage attendance.")
    if event.squad_id is not None and event.squad_id != current_user.squad_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this event.")
    unique_user_ids = list(dict.fromkeys(user_ids))
    target_squads = (
        await session.execute(select(User.id, User.squad_id).where(User.id.in_(unique_user_ids)))
    ).all()
    if len(target_squads) != len(unique_user_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more users not found.")
    if any(squad_id != current_user.squad_id for _, squad_id in target_squads):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot mark users from another squad.")


async def get_attendance_or_404(session: AsyncSession, attendance_id: int) -> Attendance:
    attendance = await session.get(Attendance, attendance_id)
    if attendance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance row not found.")
    return attendance


async def ensure_can_manage_attendance_row(
    *,
    session: AsyncSession,
    current_user: CurrentUser,
    attendance: Attendance,
) -> ScheduleEvent:
    event = await get_event_or_404(session, attendance.event_id)
    await ensure_can_manage_attendance(
        session=session,
        current_user=current_user,
        event=event,
        user_ids=[attendance.user_id],
    )
    return event


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


@router.get("/my", response_model=list[AttendanceRead])
async def my_attendance(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Attendance]:
    user_id = require_profile(current_user)
    statement = select(Attendance).where(Attendance.user_id == user_id).order_by(Attendance.updated_at.desc().nullslast())
    return list((await session.scalars(statement)).all())


@router.get("/stats/my", response_model=ReportSummary)
async def my_attendance_stats(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    user_id = require_profile(current_user)
    rows = (
        await session.execute(
            select(Attendance.status_code, func.count(Attendance.id))
            .where(Attendance.user_id == user_id)
            .group_by(Attendance.status_code)
        )
    ).all()
    total = sum(count for _, count in rows)
    return ReportSummary(
        title="Моя посещаемость",
        items=[{"status_code": status_code, "count": count, "total": total} for status_code, count in rows],
    )


@router.get("/streak/my", response_model=dict)
async def my_streak(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user_id = require_profile(current_user)
    rows = list(
        (
            await session.execute(
                select(Attendance.status_code, ScheduleEvent.start_datetime)
                .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
                .where(Attendance.user_id == user_id, Attendance.status_code != "NOT_MARKED")
                .order_by(ScheduleEvent.start_datetime.desc())
            )
        ).all()
    )
    current_streak = best_streak = 0
    temp = 0
    for status_code, _ in rows:
        if status_code == "PRESENT":
            temp += 1
            if temp > best_streak:
                best_streak = temp
        else:
            temp = 0
    # current_streak = leading consecutive PRESENT from the most recent
    for status_code, _ in rows:
        if status_code == "PRESENT":
            current_streak += 1
        else:
            break
    total = len(rows)
    present = sum(1 for sc, _ in rows if sc == "PRESENT")
    return {
        "current_streak": current_streak,
        "best_streak": best_streak,
        "total_events": total,
        "present_count": present,
        "percent": round(present / total * 100) if total else 0,
    }


@router.get("/stats/squad", response_model=ReportSummary)
async def squad_attendance_stats(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    target_squad_id = squad_id if squad_id is not None else current_user.squad_id
    if target_squad_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="squad_id is required.")
    if not can_manage_squad(current_user, target_squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this squad.")
    rows = (
        await session.execute(
            select(Attendance.status_code, func.count(Attendance.id))
            .join(User, User.id == Attendance.user_id)
            .where(User.squad_id == target_squad_id)
            .group_by(Attendance.status_code)
        )
    ).all()
    total = sum(count for _, count in rows)
    return ReportSummary(
        title="Посещаемость отделения",
        items=[{"status_code": status_code, "count": count, "total": total} for status_code, count in rows],
    )


@router.get("/events/{event_id}", response_model=list[AttendanceRead])
async def event_attendance(
    event_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Attendance]:
    event = await get_event_or_404(session, event_id)
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        statement = select(Attendance).where(Attendance.event_id == event.id).order_by(Attendance.user_id)
    else:
        if current_user.squad_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Squad is required.")
        if event.squad_id is not None and event.squad_id != current_user.squad_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this event.")
        statement = (
            select(Attendance)
            .join(User, User.id == Attendance.user_id)
            .where(Attendance.event_id == event.id, User.squad_id == current_user.squad_id)
            .order_by(Attendance.user_id)
        )
    return list((await session.scalars(statement)).all())


@router.post("/events/{event_id}/mark", response_model=list[AttendanceRead])
async def mark_event_attendance(
    event_id: int,
    payload: AttendanceMarkRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Attendance]:
    marker_id = require_profile(current_user)
    event = await get_event_or_404(session, event_id)
    user_ids = [item.user_id for item in payload.items]
    if not user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No attendance items provided.")
    await ensure_can_manage_attendance(session=session, current_user=current_user, event=event, user_ids=user_ids)

    existing = {
        item.user_id: item
        for item in (
            await session.scalars(select(Attendance).where(Attendance.event_id == event_id, Attendance.user_id.in_(user_ids)))
        ).all()
    }
    saved: list[Attendance] = []
    now = utcnow()
    for item in payload.items:
        attendance = existing.get(item.user_id)
        old_status = attendance.status_code if attendance else None
        if attendance is None:
            attendance = Attendance(event_id=event_id, user_id=item.user_id)
            session.add(attendance)
        attendance.status_code = item.status_code
        attendance.absence_reason_id = item.absence_reason_id
        attendance.custom_reason = item.custom_reason
        attendance.marked_by_user_id = marker_id
        attendance.marked_at = now
        attendance.is_draft = item.is_draft
        attendance.updated_at = now
        saved.append(attendance)
        await session.flush()
        await sync_automatic_grade(session=session, event=event, attendance=attendance, actor_id=marker_id)
        session.add(
            AttendanceHistory(
                attendance_id=attendance.id,
                old_status=old_status,
                new_status=item.status_code,
                changed_by_id=marker_id,
                change_reason=item.comment,
            )
        )

    await record_audit(
        session,
        user_id=marker_id,
        action_code="attendance.mark",
        entity_name="schedule_events",
        entity_id=event_id,
        new_value={"items": [item.model_dump(mode="json") for item in payload.items]},
    )
    await session.commit()
    for attendance in saved:
        await session.refresh(attendance)
    return saved


@router.patch("/{attendance_id}", response_model=AttendanceRead)
async def update_attendance(
    attendance_id: int,
    payload: AttendanceUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Attendance:
    marker_id = require_profile(current_user)
    attendance = await get_attendance_or_404(session, attendance_id)
    await ensure_can_manage_attendance_row(session=session, current_user=current_user, attendance=attendance)
    event = await get_event_or_404(session, attendance.event_id)
    updates = payload.model_dump(exclude_unset=True, exclude={"change_reason"})
    old = model_snapshot(attendance, list(updates))
    old_status = attendance.status_code
    for key, value in updates.items():
        setattr(attendance, key, value)
    attendance.marked_by_user_id = marker_id
    attendance.marked_at = utcnow()
    attendance.updated_at = utcnow()
    await sync_automatic_grade(session=session, event=event, attendance=attendance, actor_id=marker_id)
    session.add(
        AttendanceHistory(
            attendance_id=attendance.id,
            old_status=old_status,
            new_status=attendance.status_code,
            changed_by_id=marker_id,
            change_reason=payload.change_reason,
        )
    )
    await record_audit(
        session,
        user_id=marker_id,
        action_code="attendance.update",
        entity_name="attendance",
        entity_id=attendance.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(attendance)
    return attendance


@router.patch("/{attendance_id}/grade", response_model=AttendanceGradeRead)
async def update_attendance_grade(
    attendance_id: int,
    payload: AttendanceGradeUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> AttendanceGrade:
    setter_id = require_profile(current_user)
    attendance = await get_attendance_or_404(session, attendance_id)
    await ensure_can_manage_attendance_row(session=session, current_user=current_user, attendance=attendance)
    grade = await session.scalar(select(AttendanceGrade).where(AttendanceGrade.attendance_id == attendance_id))
    old_grade = grade.grade_value if grade else None
    now = utcnow()
    if grade is None:
        grade = AttendanceGrade(attendance_id=attendance_id, set_by_user_id=setter_id)
        session.add(grade)
    grade.grade_value = payload.grade_value
    grade.comment = payload.comment
    grade.set_by_user_id = setter_id
    grade.updated_at = now
    session.add(
        AttendanceHistory(
            attendance_id=attendance.id,
            old_grade=old_grade,
            new_grade=payload.grade_value,
            changed_by_id=setter_id,
            change_reason=payload.change_reason,
        )
    )
    await record_audit(
        session,
        user_id=setter_id,
        action_code="attendance.grade",
        entity_name="attendance",
        entity_id=attendance.id,
        old_value={"grade_value": old_grade},
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(grade)
    return grade
