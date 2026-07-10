from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import User
from ..roles import RoleLevel, ROLE_LEVELS
from ..schemas.core import UserCreate, UserRead, UserUpdate
from ..services.auth_security import bump_token_version
from ..services.sessions import delete_user_sessions
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def users(
    squad_id: int | None = None,
    role_code: str | None = None,
    status_code: str | None = None,
    limit: int = 200,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[User]:
    statement = select(User).order_by(User.full_name)
    if squad_id is not None:
        statement = statement.where(User.squad_id == squad_id)
    if role_code:
        statement = statement.where(User.role_code == role_code)
    if status_code:
        statement = statement.where(User.status_code == status_code)
    else:
        statement = statement.where(User.status_code != "ARCHIVED")
    statement = statement.offset(max(0, offset)).limit(min(max(1, limit), 500))
    return list((await session.scalars(statement)).all())


@router.get("/{user_id}", response_model=UserRead)
async def user_detail(
    user_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if payload.role_code not in ROLE_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role_code.")
    user = User(**payload.model_dump(), updated_at=datetime.now(timezone.utc))
    session.add(user)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="user.create",
        entity_name="users",
        entity_id=user.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    updates = payload.model_dump(exclude_unset=True)
    if "role_code" in updates and updates["role_code"] is not None:
        if updates["role_code"] not in ROLE_LEVELS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role_code.")
        target_level = ROLE_LEVELS.get(updates["role_code"], RoleLevel.PUBLIC_USER)
        if target_level >= current_user.role_level and current_user.role_level < RoleLevel.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign a role equal to or higher than your own.",
            )
    if current_user.role_level < RoleLevel.ADMIN:
        if user.squad_id is not None and not can_manage_squad(current_user, user.squad_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage this user.")
    old = model_snapshot(user, list(updates))
    old_status = user.status_code
    old_telegram_id = user.telegram_id
    old_role = user.role_code
    for key, value in updates.items():
        setattr(user, key, value)
    security_changed = user.status_code != old_status or user.telegram_id != old_telegram_id or user.role_code != old_role
    if security_changed:
        bump_token_version(user)
    user.updated_at = datetime.now(timezone.utc)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="user.update",
        entity_name="users",
        entity_id=user.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    if security_changed:
        await delete_user_sessions(settings, user.id)
    await session.refresh(user)
    return user
