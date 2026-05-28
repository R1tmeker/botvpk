from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import MenuCard, UserDashboardSetting
from ..roles import RoleLevel
from ..schemas.core import DashboardSettingRead, DashboardSettingsUpdate, MessageResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


@router.get("/settings", response_model=list[DashboardSettingRead])
async def dashboard_settings(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserDashboardSetting]:
    user_id = require_profile(current_user)
    statement = (
        select(UserDashboardSetting)
        .where(UserDashboardSetting.user_id == user_id)
        .order_by(UserDashboardSetting.sort_order, UserDashboardSetting.block_code)
    )
    return list((await session.scalars(statement)).all())


@router.patch("/settings", response_model=list[DashboardSettingRead])
@router.put("/settings", response_model=list[DashboardSettingRead])
async def update_dashboard_settings(
    payload: DashboardSettingsUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserDashboardSetting]:
    user_id = require_profile(current_user)
    existing = {
        item.block_code: item
        for item in (
            await session.scalars(select(UserDashboardSetting).where(UserDashboardSetting.user_id == user_id))
        ).all()
    }
    now = datetime.now(timezone.utc)
    saved: list[UserDashboardSetting] = []
    required_codes = set(
        (
            await session.scalars(
                select(MenuCard.code).where(MenuCard.is_active.is_(True), MenuCard.is_required.is_(True))
            )
        ).all()
    )
    for payload_item in payload.items:
        if payload_item.is_hidden and payload_item.block_code in required_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Required dashboard block cannot be hidden.")
        item = existing.get(payload_item.block_code)
        if item is None:
            item = UserDashboardSetting(user_id=user_id, block_code=payload_item.block_code)
            session.add(item)
        item.sort_order = payload_item.sort_order
        item.is_hidden = payload_item.is_hidden
        item.is_pinned = payload_item.is_pinned
        item.view_mode_code = payload_item.view_mode_code
        item.updated_at = now
        saved.append(item)
    await session.commit()
    for item in saved:
        await session.refresh(item)
    return sorted(saved, key=lambda item: (item.sort_order, item.block_code))


@router.post("/settings/reset", response_model=MessageResponse)
async def reset_dashboard_settings(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    items = list(
        (
            await session.scalars(select(UserDashboardSetting).where(UserDashboardSetting.user_id == user_id))
        ).all()
    )
    for item in items:
        await session.delete(item)
    await session.commit()
    return MessageResponse(detail=f"Reset {len(items)} dashboard settings.")
