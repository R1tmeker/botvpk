from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import AbsenceReason, EventResponse, Notification, ScheduleEvent, ScheduleTemplate, Setting
from ..models.user import User as UserModel
from ..roles import CONFIRMED_ROLES, RoleLevel
from ..schemas.core import (
    AbsenceReasonRead,
    EventResponseCreate,
    MessageResponse,
    ScheduleEventCreate,
    ScheduleEventRead,
    ScheduleEventUpdate,
    ScheduleTemplateCreate,
    ScheduleTemplateRead,
    ScheduleTemplateUpdate,
)
from ..utils.audit import model_snapshot, record_audit, utcnow

router = APIRouter(prefix="/schedule", tags=["schedule"])


def can_view_event(current_user: CurrentUser, event: ScheduleEvent) -> bool:
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        return True
    return event.squad_id is None or event.squad_id == current_user.squad_id


def week_parity_for_date(value: date, week_a_start: date) -> str:
    monday = value - timedelta(days=value.weekday())
    weeks = (monday - week_a_start).days // 7
    return "A" if weeks % 2 == 0 else "B"


async def get_week_a_start(session: AsyncSession) -> date | None:
    raw_value = await session.scalar(select(Setting.value).where(Setting.key == "schedule_week_a_start"))
    if not raw_value:
        return None
    try:
        parsed = date.fromisoformat(raw_value)
        return parsed - timedelta(days=parsed.weekday())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setting schedule_week_a_start must be an ISO date, for example 2026-06-02.",
        ) from exc


def serialize_event(event: ScheduleEvent, response_by_event: dict[int, str | None] | None = None) -> ScheduleEventRead:
    data = ScheduleEventRead.model_validate(event)
    if response_by_event is not None:
        data.my_response_code = response_by_event.get(event.id)
    return data


@router.get("/current-week-type")
async def current_week_type(
    session: AsyncSession = Depends(get_db_session),
    _current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
) -> dict[str, str | None]:
    week_a_start = await get_week_a_start(session)
    if week_a_start is None:
        return {"parity": None, "week_a_start": None}
    return {
        "parity": week_parity_for_date(date.today(), week_a_start),
        "week_a_start": week_a_start.isoformat(),
    }


@router.get("", response_model=list[ScheduleEventRead])
async def list_schedule(
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleEventRead]:
    statement = select(ScheduleEvent).order_by(ScheduleEvent.start_datetime)
    if from_dt:
        statement = statement.where(ScheduleEvent.start_datetime >= from_dt)
    if to_dt:
        statement = statement.where(ScheduleEvent.start_datetime <= to_dt)
    if squad_id is not None:
        statement = statement.where(ScheduleEvent.squad_id == squad_id)
    elif current_user.squad_id is not None:
        statement = statement.where((ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == current_user.squad_id))
    events = list((await session.scalars(statement)).all())
    response_by_event: dict[int, str | None] = {}
    if events and current_user.user_id is not None:
        response_rows = (
            await session.execute(
                select(EventResponse.event_id, EventResponse.response_code).where(
                    EventResponse.user_id == current_user.user_id,
                    EventResponse.event_id.in_([event.id for event in events]),
                )
            )
        ).all()
        response_by_event = {event_id: response_code for event_id, response_code in response_rows}
    return [serialize_event(event, response_by_event) for event in events]


@router.get("/today", response_model=list[ScheduleEventRead])
async def today_schedule(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScheduleEventRead]:
    today = date.today()
    start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today, time.max, tzinfo=timezone.utc)
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
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleEventRead:
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
    if event.requires_response:
        start_str = event.start_datetime.strftime("%d.%m %H:%M") if event.start_datetime else "—"
        place_str = f"\nМесто: {event.place}" if event.place else ""
        participants = (await session.scalars(
            select(UserModel).where(
                UserModel.status_code == "ACTIVE",
                UserModel.role_code.in_(CONFIRMED_ROLES),
                (UserModel.squad_id == event.squad_id) if event.squad_id else True,
            )
        )).all()
        for participant in participants:
            session.add(Notification(
                user_id=participant.id,
                type_code="SCHEDULE_POLL",
                title=event.title,
                body=f"{start_str}{place_str}\n\nОтветьте, придёте ли на занятие.",
                entity_name="schedule_events",
                entity_id=event.id,
                send_to_tg=True,
            ))
    await session.commit()
    await session.refresh(event)
    return serialize_event(event)


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
    audit_updates = payload.model_dump(exclude_unset=True, mode="json")
    old = model_snapshot(event, list(updates))
    for key, value in updates.items():
        setattr(event, key, value)
    if event.template_id is not None and updates:
        event.is_overridden = True
    event.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="schedule_event.update",
        entity_name="schedule_events",
        entity_id=event.id,
        old_value=old,
        new_value=audit_updates,
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
    if not can_manage_squad(current_user, template.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this template.")
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
    if not can_manage_squad(current_user, template.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this template.")
    week_a_start = None
    if template.week_parity is not None:
        week_a_start = await get_week_a_start(session)
        if week_a_start is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="schedule_week_a_start is required for templates with week_parity A/B.",
            )
    weekdays = {int(item.strip()) for item in template.week_days.split(",") if item.strip()}
    start_day = template.valid_from or date.today()
    end_day = min(template.valid_to or start_day + timedelta(days=days), start_day + timedelta(days=days))
    existing_events = list(
        (
            await session.scalars(
                select(ScheduleEvent).where(
                    ScheduleEvent.template_id == template.id,
                    ScheduleEvent.start_datetime >= datetime.combine(start_day, time.min),
                    ScheduleEvent.start_datetime <= datetime.combine(end_day, time.max),
                )
            )
        ).all()
    )
    existing_dates = {event.start_datetime.date() for event in existing_events}
    created: list[ScheduleEvent] = []
    current = start_day
    while current <= end_day:
        if current.isoweekday() in weekdays:
            if current in existing_dates:
                current += timedelta(days=1)
                continue
            if template.week_parity is not None and week_a_start is not None:
                if week_parity_for_date(current, week_a_start) != template.week_parity:
                    current += timedelta(days=1)
                    continue
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


@router.get("/events/{event_id}/responses")
async def event_responses(
    event_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get event responses with user info, including people who have not answered yet."""
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_view_event(current_user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this event.")
    users_statement = (
        select(UserModel)
        .where(UserModel.status_code == "ACTIVE", UserModel.role_code.in_(CONFIRMED_ROLES))
        .order_by(UserModel.squad_id.nullslast(), UserModel.full_name)
    )
    if event.squad_id is not None:
        users_statement = users_statement.where(UserModel.squad_id == event.squad_id)
    elif current_user.role_level < RoleLevel.SQUAD_COMMANDER:
        if current_user.squad_id is None:
            return []
        users_statement = users_statement.where(UserModel.squad_id == current_user.squad_id)
    users = list((await session.scalars(users_statement)).all())
    response_rows = list(
        (
            await session.scalars(
                select(EventResponse).where(EventResponse.event_id == event_id).limit(2000)
            )
        ).all()
    )
    responses_by_user = {row.user_id: row for row in response_rows}
    return [
        {
            "user_id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "squad_id": user.squad_id,
            "response_code": responses_by_user[user.id].response_code if user.id in responses_by_user else "NO_RESPONSE",
            "custom_reason": responses_by_user[user.id].custom_reason if user.id in responses_by_user else None,
            "responded_at": responses_by_user[user.id].responded_at.isoformat()
            if user.id in responses_by_user and responses_by_user[user.id].responded_at
            else None,
        }
        for user in users
    ]


@router.get("/events/{event_id}", response_model=ScheduleEventRead)
async def event_detail(
    event_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleEventRead:
    event = await session.get(ScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    if not can_view_event(current_user, event):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this event.")
    response_code = None
    if current_user.user_id is not None:
        response_code = await session.scalar(
            select(EventResponse.response_code).where(
                EventResponse.event_id == event_id,
                EventResponse.user_id == current_user.user_id,
            )
        )
    return serialize_event(event, {event.id: response_code})
