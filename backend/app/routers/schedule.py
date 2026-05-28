from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import AbsenceReason, EventResponse, ScheduleEvent, ScheduleTemplate
from ..schemas.core import AbsenceReasonRead
from ..roles import RoleLevel
from ..schemas.core import (
    EventResponseCreate,
    MessageResponse,
    ScheduleEventCreate,
    ScheduleEventRead,
    ScheduleEventUpdate,
    ScheduleTemplateCreate,
    ScheduleTemplateRead,
    ScheduleTemplateUpdate,
)
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/schedule", tags=["schedule"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def can_view_event(current_user: CurrentUser, event: ScheduleEvent) -> bool:
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        return True
    return event.squad_id is None or event.squad_id == current_user.squad_id


@router.get("", response_model=list[ScheduleEventRead])
async def list_schedule(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleEvent]:
    statement = select(ScheduleEvent).order_by(ScheduleEvent.start_datetime)
    if from_dt:
        statement = statement.where(ScheduleEvent.start_datetime >= from_dt)
    if to_dt:
        statement = statement.where(ScheduleEvent.start_datetime <= to_dt)
    if squad_id is not None:
        statement = statement.where(ScheduleEvent.squad_id == squad_id)
    elif current_user.squad_id is not None:
        statement = statement.where((ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == current_user.squad_id))
    return list((await session.scalars(statement)).all())


@router.get("/today", response_model=list[ScheduleEventRead])
async def today_schedule(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleEvent]:
    today = date.today()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    return await list_schedule(start, end, None, current_user, session)


@router.get("/absence-reasons", response_model=list[AbsenceReasonRead])
async def absence_reasons(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[AbsenceReason]:
    return list(
        (
            await session.scalars(
                select(AbsenceReason)
                .where(AbsenceReason.is_active.is_(True))
                .order_by(AbsenceReason.sort_order)
            )
        ).all()
    )


@router.post("/events/{event_id}/respond", response_model=MessageResponse)
async def respond_event(
    event_id: int,
    payload: EventResponseCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_view_event(current_user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot respond to this event.")
    now = utcnow()
    if event.response_deadline_at and now > event.response_deadline_at and current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Response deadline has passed.")
    if payload.response_code in {"NOT_COMING", "NO"} and event.requires_response:
        if payload.absence_reason_id is None and not payload.custom_reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Absence reason is required.")
        if payload.absence_reason_id is not None:
            reason = await session.get(AbsenceReason, payload.absence_reason_id)
            if reason is None or not reason.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Absence reason not found.")
            if reason.requires_comment and not payload.custom_reason:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom reason is required.")
    response = await session.scalar(
        select(EventResponse).where(EventResponse.event_id == event_id, EventResponse.user_id == current_user.user_id)
    )
    if response:
        response.response_code = payload.response_code
        response.absence_reason_id = payload.absence_reason_id
        response.custom_reason = payload.custom_reason
        response.responded_at = now
        response.source_code = "MINI_APP"
    else:
        session.add(
            EventResponse(
                event_id=event_id,
                user_id=current_user.user_id,
                response_code=payload.response_code,
                absence_reason_id=payload.absence_reason_id,
                custom_reason=payload.custom_reason,
                source_code="MINI_APP",
            )
        )
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_event.respond",
        entity_name="schedule_events",
        entity_id=event_id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return MessageResponse(detail="Response saved.")


@router.post("/events", response_model=ScheduleEventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: ScheduleEventCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleEvent:
    if not can_manage_squad(current_user, payload.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this squad.")
    event = ScheduleEvent(created_by_user_id=current_user.user_id, **payload.model_dump())
    session.add(event)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_event.create",
        entity_name="schedule_events",
        entity_id=event.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/events/{event_id}", response_model=ScheduleEventRead)
async def update_event(
    event_id: int,
    payload: ScheduleEventUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleEvent:
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_manage_squad(current_user, event.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this event.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(event, list(updates))
    for key, value in updates.items():
        setattr(event, key, value)
    event.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_event.update",
        entity_name="schedule_events",
        entity_id=event.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/events/{event_id}", response_model=MessageResponse)
async def delete_event(
    event_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_manage_squad(current_user, event.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this event.")
    old_status = event.status_code
    event.status_code = "CANCELLED"
    event.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_event.cancel",
        entity_name="schedule_events",
        entity_id=event.id,
        old_value={"status_code": old_status, "title": event.title, "start_datetime": event.start_datetime.isoformat()},
        new_value={"status_code": event.status_code},
    )
    await session.commit()
    return MessageResponse(detail="Event cancelled.")


@router.get("/templates", response_model=list[ScheduleTemplateRead])
async def list_templates(
    active_only: bool = True,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleTemplate]:
    statement = select(ScheduleTemplate).order_by(ScheduleTemplate.created_at.desc())
    if active_only:
        statement = statement.where(ScheduleTemplate.is_active.is_(True))
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where((ScheduleTemplate.squad_id.is_(None)) | (ScheduleTemplate.squad_id == current_user.squad_id))
    return list((await session.scalars(statement)).all())


@router.post("/templates", response_model=ScheduleTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ScheduleTemplateCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleTemplate:
    template = ScheduleTemplate(created_by_user_id=current_user.user_id, **payload.model_dump())
    session.add(template)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_template.create",
        entity_name="schedule_templates",
        entity_id=template.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=ScheduleTemplateRead)
async def update_template(
    template_id: int,
    payload: ScheduleTemplateUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleTemplate:
    template = await session.get(ScheduleTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(template, list(updates))
    for key, value in updates.items():
        setattr(template, key, value)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_template.update",
        entity_name="schedule_templates",
        entity_id=template.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(template)
    return template


@router.post("/templates/{template_id}/generate", response_model=list[ScheduleEventRead])
async def generate_template_events(
    template_id: int,
    days: int = 30,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleEvent]:
    template = await session.get(ScheduleTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    weekdays = {int(item.strip()) for item in template.week_days.split(",") if item.strip()}
    start_day = template.valid_from or date.today()
    end_day = min(template.valid_to or start_day + timedelta(days=days), start_day + timedelta(days=days))
    created: list[ScheduleEvent] = []
    current = start_day
    while current <= end_day:
        if current.isoweekday() in weekdays:
            start_dt = datetime.combine(current, template.start_time)
            end_dt = datetime.combine(current, template.end_time) if template.end_time else None
            deadline = (
                start_dt - timedelta(minutes=template.response_deadline_minutes)
                if template.response_deadline_minutes
                else None
            )
            event = ScheduleEvent(
                template_id=template.id,
                event_type_code="CLASS",
                title=template.title,
                description=template.description,
                start_datetime=start_dt,
                end_datetime=end_dt,
                place=template.place,
                squad_id=template.squad_id,
                requires_response=template.requires_response,
                response_deadline_at=deadline,
                created_by_user_id=current_user.user_id,
            )
            session.add(event)
            created.append(event)
        current += timedelta(days=1)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_template.generate",
        entity_name="schedule_templates",
        entity_id=template.id,
        new_value={"days": days, "created": len(created)},
    )
    await session.commit()
    for event in created:
        await session.refresh(event)
    return created


@router.get("/events/{event_id}", response_model=ScheduleEventRead)
@router.get("/{event_id}", response_model=ScheduleEventRead)
async def event_detail(
    event_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleEvent:
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_view_event(current_user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this event.")
    return event
