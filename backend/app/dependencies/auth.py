from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..models import User
from ..roles import RoleLevel, role_level
from ..utils.jwt import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user: User | None
    user_id: int | None
    telegram_id: int
    role_code: str
    squad_id: int | None

    @property
    def role_level(self) -> RoleLevel:
        return role_level(self.role_code)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.") from exc

    telegram_id = payload.get("telegram_id")
    if telegram_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    user_id = payload.get("user_id")
    user = None
    if user_id is not None:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User from token not found.")
    return CurrentUser(
        user=user,
        user_id=user.id if user else None,
        telegram_id=int(telegram_id),
        role_code=user.role_code if user else payload.get("role_code", "PUBLIC_USER"),
        squad_id=user.squad_id if user else payload.get("squad_id"),
    )


def require_role(min_role: RoleLevel):
    async def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role_level < min_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role.")
        return current_user

    return dependency


def is_platoon_or_admin(current_user: CurrentUser) -> bool:
    return current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER


def can_manage_squad(current_user: CurrentUser, squad_id: int | None) -> bool:
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        return True
    if current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER and squad_id == current_user.squad_id:
        return True
    return False
