from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Notification, NotificationPreference as NotificationPreferenceModel
from ..roles import RoleLevel
from ..schemas.core import MessageResponse, NotificationRead
from ..schemas.product import NotificationPreference, NotificationPreferencesUpdate
from ..utils.audit import record_audit, utcnow

router = APIRouter(prefix="/notifications", tags=["notifications"])
me_router = APIRouter(prefix="/me", tags=["notifications"])

NOTIFICATION_CATEGORIES = (
    "SCHEDULE",
    "ATTENDANCE",
    "NORMATIVES",
    "ANNOUNCEMENTS",
    "APPEALS",
    "SYSTEM",
)


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


@router.get("/preferences/me", response_model=list[NotificationPreference], include_in_schema=False)
@router.get("/me/preferences", response_model=list[NotificationPreference], include_in_schema=False)
async def legacy_notification_preferences(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NotificationPreference]:
    return await get_notification_preferences(current_user, session)


async def get_notification_preferences(
    current_user: CurrentUser,
    session: AsyncSession,
) -> list[NotificationPreference]:
    user_id = require_profile(current_user)
    stored = {
        item.category_code: item
        for item in (
            await session.scalars(
                select(NotificationPreferenceModel).where(NotificationPreferenceModel.user_id == user_id)
            )
        ).all()
    }
    return [
        NotificationPreference.model_validate(stored[category], from_attributes=True)
        if category in stored
        else NotificationPreference(category_code=category)
        for category in NOTIFICATION_CATEGORIES
    ]


async def put_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: CurrentUser,
    session: AsyncSession,
) -> list[NotificationPreference]:
    user_id = require_profile(current_user)
    categories = [item.category_code.upper() for item in payload.items]
    if len(categories) != len(set(categories)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate notification category.")
    unknown = set(categories) - set(NOTIFICATION_CATEGORIES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown notification categories: {', '.join(sorted(unknown))}",
        )
    existing = {
        item.category_code: item
        for item in (
            await session.scalars(
                select(NotificationPreferenceModel).where(NotificationPreferenceModel.user_id == user_id)
            )
        ).all()
    }
    now = utcnow()
    for payload_item in payload.items:
        category = payload_item.category_code.upper()
        item = existing.get(category)
        if item is None:
            item = NotificationPreferenceModel(user_id=user_id, category_code=category)
            session.add(item)
        for field, value in payload_item.model_dump(exclude={"category_code"}).items():
            setattr(item, field, value)
        item.updated_at = now
    await record_audit(
        session,
        user_id=user_id,
        action_code="notifications.preferences.update",
        entity_name="notification_preferences",
        new_value={"items": [item.model_dump(mode="json") for item in payload.items]},
    )
    await session.commit()
    return await get_notification_preferences(current_user, session)


@me_router.get("/notification-preferences", response_model=list[NotificationPreference])
async def my_notification_preferences(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NotificationPreference]:
    return await get_notification_preferences(current_user, session)


@me_router.put("/notification-preferences", response_model=list[NotificationPreference])
async def update_my_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NotificationPreference]:
    return await put_notification_preferences(payload, current_user, session)
