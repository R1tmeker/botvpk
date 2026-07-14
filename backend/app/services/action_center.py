from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Appeal,
    Attendance,
    AttendanceHistory,
    EventResponse,
    JoinApplication,
    NormativeSubmission,
    Notification,
    ScheduleEvent,
    User,
)
from ..roles import CONFIRMED_ROLES, RoleLevel
from ..utils.audit import record_audit
from .attendance import sync_automatic_grade


class ActionCenterError(ValueError):
    pass


def _scoped_squad_id(role_level: RoleLevel, squad_id: int | None) -> int | None:
    if role_level >= RoleLevel.SQUAD_COMMANDER:
        return None
    if squad_id is None:
        raise ActionCenterError("Для массового действия требуется отделение.")
    return squad_id


async def _unclosed_events(
    session: AsyncSession,
    *,
    now: datetime,
    scoped_squad_id: int | None,
) -> list[ScheduleEvent]:
    query = select(ScheduleEvent).where(
        ScheduleEvent.status_code != "CANCELLED",
        ScheduleEvent.start_datetime < now,
        ScheduleEvent.start_datetime >= now - timedelta(days=14),
    )
    if scoped_squad_id is not None:
        query = query.where(
            (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == scoped_squad_id)
        )
    result: list[ScheduleEvent] = []
    for event in (await session.scalars(query.limit(100))).all():
        marked = int(
            await session.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.event_id == event.id,
                    Attendance.status_code != "NOT_MARKED",
                    Attendance.is_draft.is_(False),
                )
            )
            or 0
        )
        if marked == 0:
            result.append(event)
    return result


async def _send_response_reminders(
    session: AsyncSession,
    *,
    now: datetime,
    scoped_squad_id: int | None,
) -> int:
    event_query = select(ScheduleEvent).where(
        ScheduleEvent.requires_response.is_(True),
        ScheduleEvent.status_code != "CANCELLED",
        ScheduleEvent.start_datetime >= now,
        ScheduleEvent.start_datetime <= now + timedelta(days=14),
    )
    if scoped_squad_id is not None:
        event_query = event_query.where(
            (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == scoped_squad_id)
        )
    affected = 0
    for event in (await session.scalars(event_query.limit(100))).all():
        target_squad_id = event.squad_id if event.squad_id is not None else scoped_squad_id
        user_query = select(User).where(
            User.status_code == "ACTIVE",
            User.role_code.in_(CONFIRMED_ROLES),
        )
        if target_squad_id is not None:
            user_query = user_query.where(User.squad_id == target_squad_id)
        users = list((await session.scalars(user_query)).all())
        if not users:
            continue
        user_ids = [user.id for user in users]
        answered = set(
            (
                await session.scalars(
                    select(EventResponse.user_id).where(
                        EventResponse.event_id == event.id,
                        EventResponse.user_id.in_(user_ids),
                    )
                )
            ).all()
        )
        recent = set(
            (
                await session.scalars(
                    select(Notification.user_id).where(
                        Notification.user_id.in_(user_ids),
                        Notification.type_code == "EVENT_RESPONSE_REMINDER",
                        Notification.entity_name == "schedule_events",
                        Notification.entity_id == event.id,
                        Notification.created_at >= now - timedelta(hours=24),
                    )
                )
            ).all()
        )
        for user in users:
            if user.id in answered or user.id in recent:
                continue
            session.add(
                Notification(
                    user_id=user.id,
                    type_code="EVENT_RESPONSE_REMINDER",
                    category_code="SCHEDULE",
                    title="Нужен ответ на событие",
                    body=f"Подтвердите участие: {event.title}",
                    entity_name="schedule_events",
                    entity_id=event.id,
                    deep_link=f"/schedule?event={event.id}",
                    send_to_tg=True,
                )
            )
            affected += 1
    return affected


async def _assign_pending_normatives(
    session: AsyncSession,
    *,
    actor_id: int,
    scoped_squad_id: int | None,
    now: datetime,
) -> int:
    query = (
        select(NormativeSubmission)
        .join(User, User.id == NormativeSubmission.user_id)
        .where(
            NormativeSubmission.status_code.in_(("PENDING", "SUBMITTED", "PENDING_REVIEW")),
            NormativeSubmission.reviewed_by_id.is_(None),
        )
    )
    if scoped_squad_id is not None:
        query = query.where(User.squad_id == scoped_squad_id)
    items = list((await session.scalars(query.limit(500).with_for_update())).all())
    for item in items:
        item.reviewed_by_id = actor_id
        item.updated_at = now
    return len(items)


async def _assign_appeals(
    session: AsyncSession,
    *,
    actor_id: int,
    scoped_squad_id: int | None,
    now: datetime,
) -> int:
    query = (
        select(Appeal)
        .join(User, User.id == Appeal.author_user_id)
        .where(Appeal.status_code == "CREATED", Appeal.assignee_user_id.is_(None))
    )
    if scoped_squad_id is not None:
        query = query.where(User.squad_id == scoped_squad_id)
    items = list((await session.scalars(query.limit(500).with_for_update())).all())
    for item in items:
        item.assignee_user_id = actor_id
        item.status_code = "IN_PROGRESS"
        item.updated_at = now
    return len(items)


async def _mark_unclosed_present(
    session: AsyncSession,
    *,
    actor_id: int,
    scoped_squad_id: int | None,
    now: datetime,
) -> int:
    affected = 0
    for event in await _unclosed_events(session, now=now, scoped_squad_id=scoped_squad_id):
        target_squad_id = event.squad_id if event.squad_id is not None else scoped_squad_id
        user_query = select(User.id).where(
            User.status_code == "ACTIVE",
            User.role_code.in_(CONFIRMED_ROLES),
        )
        if target_squad_id is not None:
            user_query = user_query.where(User.squad_id == target_squad_id)
        user_ids = list((await session.scalars(user_query)).all())
        if not user_ids:
            continue
        await session.execute(
            insert(Attendance)
            .values(
                [
                    {
                        "event_id": event.id,
                        "user_id": user_id,
                        "status_code": "NOT_MARKED",
                        "source_code": "COMMANDER",
                        "is_draft": False,
                    }
                    for user_id in user_ids
                ]
            )
            .on_conflict_do_nothing(index_elements=["event_id", "user_id"])
        )
        rows = list(
            (
                await session.scalars(
                    select(Attendance)
                    .where(Attendance.event_id == event.id, Attendance.user_id.in_(user_ids))
                    .with_for_update()
                )
            ).all()
        )
        for attendance in rows:
            if attendance.status_code != "NOT_MARKED":
                continue
            old_status = attendance.status_code
            old_source = attendance.source_code
            attendance.status_code = "PRESENT"
            attendance.source_code = "COMMANDER"
            attendance.marked_by_user_id = actor_id
            attendance.marked_at = now
            attendance.updated_at = now
            attendance.is_draft = False
            session.add(
                AttendanceHistory(
                    attendance_id=attendance.id,
                    old_status=old_status,
                    new_status="PRESENT",
                    old_source_code=old_source,
                    new_source_code="COMMANDER",
                    changed_by_id=actor_id,
                    change_reason="Массовое действие из центра командования",
                )
            )
            await sync_automatic_grade(
                session=session,
                event=event,
                attendance=attendance,
                actor_id=actor_id,
            )
            affected += 1
    return affected


async def _claim_overdue_applications(
    session: AsyncSession,
    *,
    actor_id: int,
    now: datetime,
) -> int:
    items = list(
        (
            await session.scalars(
                select(JoinApplication)
                .where(
                    JoinApplication.status_code == "NEW",
                    JoinApplication.created_at < now - timedelta(days=2),
                    JoinApplication.reviewed_by_user_id.is_(None),
                )
                .limit(500)
                .with_for_update()
            )
        ).all()
    )
    for item in items:
        item.reviewed_by_user_id = actor_id
        item.updated_at = now
    return len(items)


async def _retry_failed_notifications(session: AsyncSession, *, now: datetime) -> int:
    items = list(
        (
            await session.scalars(
                select(Notification)
                .where(Notification.delivery_error.is_not(None))
                .limit(500)
                .with_for_update()
            )
        ).all()
    )
    for item in items:
        item.delivery_error = None
        item.deliver_after = now
    return len(items)


async def execute_action_item(
    session: AsyncSession,
    *,
    item_code: str,
    action_code: str,
    actor_id: int,
    role_level: RoleLevel,
    squad_id: int | None,
) -> int:
    now = datetime.now(timezone.utc)
    scoped_squad_id = _scoped_squad_id(role_level, squad_id)
    allowed = {
        ("MISSING_EVENT_RESPONSES", "send_reminder"),
        ("PENDING_NORMATIVES", "assign_reviewer"),
        ("UNPROCESSED_APPEALS", "assign"),
        ("UNCLOSED_ATTENDANCE", "mark_all_present"),
        ("OVERDUE_APPLICATIONS", "assign_reviewer"),
        ("NOTIFICATION_DELIVERY_ERRORS", "retry_delivery"),
    }
    if (item_code, action_code) not in allowed:
        raise ActionCenterError("Это массовое действие не поддерживается.")
    if item_code == "OVERDUE_APPLICATIONS" and role_level < RoleLevel.SQUAD_COMMANDER:
        raise ActionCenterError("Недостаточно прав для работы с заявками.")
    if item_code == "NOTIFICATION_DELIVERY_ERRORS" and role_level < RoleLevel.ADMIN:
        raise ActionCenterError("Недостаточно прав для повторной доставки.")

    try:
        if item_code == "MISSING_EVENT_RESPONSES":
            affected = await _send_response_reminders(
                session,
                now=now,
                scoped_squad_id=scoped_squad_id,
            )
        elif item_code == "PENDING_NORMATIVES":
            affected = await _assign_pending_normatives(
                session,
                actor_id=actor_id,
                scoped_squad_id=scoped_squad_id,
                now=now,
            )
        elif item_code == "UNPROCESSED_APPEALS":
            affected = await _assign_appeals(
                session,
                actor_id=actor_id,
                scoped_squad_id=scoped_squad_id,
                now=now,
            )
        elif item_code == "UNCLOSED_ATTENDANCE":
            affected = await _mark_unclosed_present(
                session,
                actor_id=actor_id,
                scoped_squad_id=scoped_squad_id,
                now=now,
            )
        elif item_code == "OVERDUE_APPLICATIONS":
            affected = await _claim_overdue_applications(session, actor_id=actor_id, now=now)
        else:
            affected = await _retry_failed_notifications(session, now=now)
        await record_audit(
            session,
            user_id=actor_id,
            action_code=f"dashboard.action.{action_code}",
            entity_name="dashboard_action_items",
            new_value={"item_code": item_code, "affected": affected},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return affected
