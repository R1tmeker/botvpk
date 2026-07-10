from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..dependencies.auth import CurrentUser, require_role
from ..roles import RoleLevel
from ..services.realtime import event_stream

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    return StreamingResponse(
        event_stream(settings, request, user_id=current_user.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
