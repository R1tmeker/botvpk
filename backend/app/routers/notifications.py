from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Notification
from ..roles import RoleLevel
from ..schemas.core import MessageResponse, NotificationRead
from ..utils.audit import record_audit, utcnow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


@router.get("", response_model=list[NotificationRead])
async def notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Notification]:
    user_id = require_profile(current_user)
    statement = select(Notification).where(Notification.user_id == user_id).order_by(
        Notification.is_pinned.desc(),
        Notification.created_at.desc(),
    )
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))
    statement = statement.limit(min(limit, 200)).offset(offset)
    return list((await session.scalars(statement)).all())


@router.post("/{notification_id}/read", response_model=NotificationRead)
@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def read_notification(
    notification_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Notification:
    user_id = require_profile(current_user)
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notification.is_read = True
    notification.read_at = utcnow()
    await session.commit()
    await session.refresh(notification)
    return notification


@router.post("/read-all", response_model=MessageResponse)
async def read_all_notifications(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    unread = list(
        (
            await session.scalars(
                select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
            )
        ).all()
    )
    now = utcnow()
    for notification in unread:
        notification.is_read = True
        notification.read_at = now
    await record_audit(
        session,
        user_id=user_id,
        action_code="notifications.read_all",
        entity_name="notifications",
        new_value={"count": len(unread)},
    )
    await session.commit()
    return MessageResponse(detail=f"Marked {len(unread)} notifications as read.")
