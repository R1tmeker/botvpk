from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..roles import RoleLevel
from ..services.realtime import event_stream

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    # Authentication has finished. A long-lived stream must not occupy a DB connection.
    await session.close()
    return StreamingResponse(
        event_stream(settings, request, user_id=current_user.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
