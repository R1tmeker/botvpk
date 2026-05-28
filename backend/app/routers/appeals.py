from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Appeal, AppealMessage
from ..roles import RoleLevel
from ..schemas.core import AppealCreate, AppealMessageCreate, AppealMessageRead, AppealRead, AppealUpdate
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/appeals", tags=["appeals"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def can_view_appeal(appeal: Appeal, current_user: CurrentUser) -> bool:
    return current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER or appeal.author_user_id == current_user.user_id


async def get_appeal_or_404(session: AsyncSession, appeal_id: int) -> Appeal:
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found.")
    return appeal


@router.get("", response_model=list[AppealRead])
async def appeals(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Appeal]:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = select(Appeal).order_by(Appeal.created_at.desc())
    else:
        statement = select(Appeal).where(Appeal.author_user_id == current_user.user_id).order_by(Appeal.created_at.desc())
    return list((await session.scalars(statement)).all())


@router.post("", response_model=AppealRead, status_code=status.HTTP_201_CREATED)
async def create_appeal(
    payload: AppealCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    author_id = require_profile(current_user)
    appeal = Appeal(author_user_id=author_id, **payload.model_dump())
    session.add(appeal)
    await session.flush()
    session.add(AppealMessage(appeal_id=appeal.id, author_id=author_id, body=payload.description))
    await record_audit(
        session,
        user_id=author_id,
        action_code="appeal.create",
        entity_name="appeals",
        entity_id=appeal.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(appeal)
    return appeal


@router.get("/{appeal_id}", response_model=AppealRead)
async def appeal_detail(
    appeal_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    appeal = await get_appeal_or_404(session, appeal_id)
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this appeal.")
    return appeal


@router.patch("/{appeal_id}", response_model=AppealRead)
async def update_appeal(
    appeal_id: int,
    payload: AppealUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    user_id = require_profile(current_user)
    appeal = await get_appeal_or_404(session, appeal_id)
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(appeal, list(updates))
    for key, value in updates.items():
        setattr(appeal, key, value)
    appeal.updated_at = utcnow()
    if appeal.status_code in {"CLOSED", "RESOLVED"} and appeal.closed_at is None:
        appeal.closed_at = utcnow()
    await record_audit(
        session,
        user_id=user_id,
        action_code="appeal.update",
        entity_name="appeals",
        entity_id=appeal.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(appeal)
    return appeal


@router.get("/{appeal_id}/messages", response_model=list[AppealMessageRead])
async def appeal_messages(
    appeal_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[AppealMessage]:
    appeal = await get_appeal_or_404(session, appeal_id)
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this appeal.")
    statement = select(AppealMessage).where(AppealMessage.appeal_id == appeal_id).order_by(AppealMessage.created_at)
    return list((await session.scalars(statement)).all())


@router.post("/{appeal_id}/messages", response_model=AppealMessageRead, status_code=status.HTTP_201_CREATED)
async def create_appeal_message(
    appeal_id: int,
    payload: AppealMessageCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> AppealMessage:
    user_id = require_profile(current_user)
    appeal = await get_appeal_or_404(session, appeal_id)
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot write to this appeal.")
    message = AppealMessage(appeal_id=appeal.id, author_id=user_id, body=payload.body)
    session.add(message)
    appeal.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        action_code="appeal.message",
        entity_name="appeals",
        entity_id=appeal.id,
        new_value={"message_id": message.id},
    )
    await session.commit()
    await session.refresh(message)
    return message
