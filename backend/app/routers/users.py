from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user, require_role
from ..models import User
from ..roles import RoleLevel, ROLE_LEVELS
from ..schemas.core import UserCreate, UserRead, UserUpdate
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def users(
    squad_id: int | None = None,
    role_code: str | None = None,
    status_code: str | None = None,
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
    user = User(**payload.model_dump(), updated_at=datetime.utcnow())
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
) -> User:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    updates = payload.model_dump(exclude_unset=True)
    if "role_code" in updates and updates["role_code"] not in ROLE_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role_code.")
    old = model_snapshot(user, list(updates))
    for key, value in updates.items():
        setattr(user, key, value)
    user.updated_at = datetime.utcnow()
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
    await session.refresh(user)
    return user
