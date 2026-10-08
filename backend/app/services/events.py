from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AbsenceReason, EventResponse, ScheduleEvent
from ..roles import RoleLevel
from .event_response_policy import validate_event_available, validate_response_details


async def respond_to_event(
    session: AsyncSession,
    *,
    event: ScheduleEvent,
    user_id: int,
    role: RoleLevel,
    squad_id: int | None,
    response_code: str,
    source_code: str,
    absence_reason_id: int | None = None,
    custom_reason: str | None = None,
    now: datetime | None = None,
) -> EventResponse:
    now = now or datetime.now(timezone.utc)
    validate_event_available(event, role=role, squad_id=squad_id, now=now)
    reason = await session.get(AbsenceReason, absence_reason_id) if absence_reason_id is not None else None
    code, reason_id, comment = validate_response_details(
        response_code,
        requires_response=event.requires_response,
        absence_reason_id=absence_reason_id,
        reason=reason,
        custom_reason=custom_reason,
    )
    return await save_event_response(
        session, event_id=event.id, user_id=user_id, response_code=code,
        source_code=source_code, absence_reason_id=reason_id, custom_reason=comment, responded_at=now,
    )


async def save_event_response(
    session: AsyncSession,
    *,
    event_id: int,
    user_id: int,
    response_code: str,
    source_code: str,
    absence_reason_id: int | None = None,
    custom_reason: str | None = None,
    responded_at: datetime | None = None,
) -> EventResponse:
    response = await session.scalar(
        select(EventResponse).where(EventResponse.event_id == event_id, EventResponse.user_id == user_id)
    )
    if response is None:
        response = EventResponse(event_id=event_id, user_id=user_id)
        session.add(response)
    response.response_code = response_code
    response.absence_reason_id = absence_reason_id
    response.custom_reason = custom_reason
    response.responded_at = responded_at or datetime.now(timezone.utc)
    response.source_code = source_code
    return response
