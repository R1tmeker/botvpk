from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Announcement, Notification, User
from ..roles import RoleLevel
from ..schemas.core import AnnouncementCreate, AnnouncementRead, AnnouncementUpdate, MessageResponse
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/announcements", tags=["announcements"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def assert_can_target(payload: AnnouncementCreate | AnnouncementUpdate, current_user: CurrentUser) -> None:
    target_type = payload.target_type
    target_squad_id = payload.target_squad_id
    if target_type is None:
        return
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return
    if current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        if target_type != "SQUAD":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Squad commanders can target only a squad.")
        if target_squad_id not in {None, current_user.squad_id}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot target another squad.")
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage announcements.")


def announcement_visible(item: Announcement, current_user: CurrentUser) -> bool:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return True
    if item.status_code not in {"SENT", "PUBLISHED"}:
        return False
    if item.target_type == "ALL":
        return True
    if item.target_type == "SQUAD":
        return item.target_squad_id == current_user.squad_id
    if item.target_type == "ROLE":
        return item.target_role_code == current_user.role_code
    return False


async def users_for_announcement(
    session: AsyncSession,
    announcement: Announcement,
    current_user: CurrentUser,
) -> list[User]:
    statement = select(User).where(User.status_code == "ACTIVE")
    if announcement.target_type == "ALL":
        if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send to all squads.")
    elif announcement.target_type == "SQUAD":
        target_squad_id = announcement.target_squad_id or current_user.squad_id
        if target_squad_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_squad_id is required.")
        if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER and target_squad_id != current_user.squad_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send to this squad.")
        statement = statement.where(User.squad_id == target_squad_id)
    elif announcement.target_type == "ROLE":
        if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send by role.")
        statement = statement.where(User.role_code == announcement.target_role_code)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported target_type.")
    return list((await session.scalars(statement)).all())


@router.get("", response_model=list[AnnouncementRead])
async def announcements(
    include_drafts: bool = False,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Announcement]:
    statement = select(Announcement).order_by(Announcement.created_at.desc())
    if not include_drafts or current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        statement = statement.where(Announcement.status_code.in_(("SENT", "PUBLISHED")))
    items = list((await session.scalars(statement)).all())
    return [item for item in items if announcement_visible(item, current_user)]


@router.get("/{announcement_id}", response_model=AnnouncementRead)
async def announcement_detail(
    announcement_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Announcement:
    item = await session.get(Announcement, announcement_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    if not announcement_visible(item, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this announcement.")
    return item


@router.post("", response_model=AnnouncementRead, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    payload: AnnouncementCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Announcement:
    author_id = require_profile(current_user)
    assert_can_target(payload, current_user)
    values = payload.model_dump()
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER and values.get("target_squad_id") is None:
        values["target_squad_id"] = current_user.squad_id
    item = Announcement(created_by_id=author_id, **values)
    session.add(item)
    await session.flush()
    await record_audit(
        session,
        user_id=author_id,
        action_code="announcement.create",
        entity_name="announcements",
        entity_id=item.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/{announcement_id}", response_model=AnnouncementRead)
async def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Announcement:
    user_id = require_profile(current_user)
    item = await session.get(Announcement, announcement_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    assert_can_target(payload, current_user)
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER and item.target_squad_id != current_user.squad_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another squad announcement.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(item, list(updates))
    for key, value in updates.items():
        setattr(item, key, value)
    await record_audit(
        session,
        user_id=user_id,
        action_code="announcement.update",
        entity_name="announcements",
        entity_id=item.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/{announcement_id}/send", response_model=MessageResponse)
async def send_announcement(
    announcement_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    item = await session.get(Announcement, announcement_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")
    users = await users_for_announcement(session, item, current_user)
    now = utcnow()
    item.status_code = "SENT"
    item.sent_at = now
    if item.send_to_app:
        for user in users:
            session.add(
                Notification(
                    user_id=user.id,
                    type_code="ANNOUNCEMENT",
                    title=item.title,
                    body=item.body,
                    entity_name="announcements",
                    entity_id=item.id,
                    send_to_tg=item.send_to_tg,
                )
            )
    await record_audit(
        session,
        user_id=user_id,
        action_code="announcement.send",
        entity_name="announcements",
        entity_id=item.id,
        new_value={"recipients": len(users)},
    )
    await session.commit()
    return MessageResponse(detail=f"Announcement sent to {len(users)} users.")
