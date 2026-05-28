from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import require_role
from ...models import User
from ...roles import RoleLevel
from ...schemas.core import UserRead

router = APIRouter(prefix="/admin/users", tags=["admin:users"])


@router.get("", response_model=list[UserRead])
async def admin_users(
    squad_id: int | None = None,
    role_code: str | None = None,
    status_code: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
) -> list[User]:
    statement = select(User).order_by(User.squad_id.nullslast(), User.full_name)
    if squad_id is not None:
        statement = statement.where(User.squad_id == squad_id)
    if role_code is not None:
        statement = statement.where(User.role_code == role_code)
    if status_code is not None:
        statement = statement.where(User.status_code == status_code)
    return list((await session.scalars(statement)).all())
