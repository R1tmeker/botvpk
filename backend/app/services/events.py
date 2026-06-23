from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EventResponse


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
