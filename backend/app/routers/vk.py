from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..roles import RoleLevel
from ..schemas.auth import VkLinkCodeResponse, VkStatusResponse
from ..utils.audit import record_audit
from ..utils.channel_link import issue_link_code

router = APIRouter(prefix="/auth/vk", tags=["vk"])


@router.get("/status", response_model=VkStatusResponse)
async def vk_status(
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> VkStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return VkStatusResponse(linked=user.vk_id is not None, vk_id=user.vk_id, bot_url=settings.vk_bot_url)


@router.post("/link-code", response_model=VkLinkCodeResponse)
async def vk_link_code(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> VkLinkCodeResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    if current_user.role_level < RoleLevel.PARTICIPANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="VK linking is available only to confirmed members.",
        )
    code, expires_at = await issue_link_code(session, user.id, channel="VK")
    await record_audit(
        session,
        user_id=user.id,
        action_code="vk.link_code.issue",
        entity_name="users",
        entity_id=user.id,
    )
    await session.commit()
    return VkLinkCodeResponse(code=code, expires_at=expires_at)


@router.delete("/", response_model=VkStatusResponse)
async def vk_unlink(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> VkStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    old_vk = user.vk_id
    user.vk_id = None
    user.updated_at = datetime.now(timezone.utc)
    await record_audit(
        session,
        user_id=user.id,
        action_code="vk.unlink",
        entity_name="users",
        entity_id=user.id,
        old_value={"vk_id": old_vk},
    )
    await session.commit()
    return VkStatusResponse(linked=False, vk_id=None, bot_url=settings.vk_bot_url)
