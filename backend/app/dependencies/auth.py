from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..models import User
from ..roles import RoleLevel, role_level
from ..services.sessions import AuthSession, SessionUnavailableError, csrf_matches, resolve_auth_session


@dataclass(frozen=True)
class CurrentUser:
    user: User | None
    user_id: int | None
    telegram_id: int
    role_code: str
    squad_id: int | None
    auth_session: AuthSession
    session_token: str

    @property
    def role_level(self) -> RoleLevel:
        return role_level(self.role_code)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authenticated session.")
    try:
        auth_session = await resolve_auth_session(settings, token)
    except SessionUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Session storage unavailable.") from exc
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked.")

    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        csrf_header = request.headers.get("X-CSRF-Token", "")
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name, "")
        if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie or not csrf_matches(settings, auth_session, csrf_header):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")

    user = await session.scalar(select(User).where(User.id == auth_session.user_id))
    if user is None or user.telegram_id != auth_session.telegram_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session user not found.")
    if user.status_code != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive.")
    if auth_session.token_version != (user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked.")
    return CurrentUser(
        user=user,
        user_id=user.id,
        telegram_id=int(user.telegram_id or 0),
        role_code=user.role_code,
        squad_id=user.squad_id,
        auth_session=auth_session,
        session_token=token,
    )


def require_role(min_role: RoleLevel):
    async def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role_level < min_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role.")
        return current_user

    return dependency


async def require_step_up(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.auth_session.step_up_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recent authentication is required.")
    return current_user


def is_platoon_or_admin(current_user: CurrentUser) -> bool:
    return current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER


def can_manage_squad(current_user: CurrentUser, squad_id: int | None) -> bool:
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        return True
    if current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER and squad_id == current_user.squad_id:
        return True
    return False
