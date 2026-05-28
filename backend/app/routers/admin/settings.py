from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import Setting
from ...roles import RoleLevel
from ...schemas.core import SettingRead, SettingsPatch
from ...utils.audit import record_audit

router = APIRouter(prefix="/admin/settings", tags=["admin:settings"])


@router.get("", response_model=list[SettingRead])
async def settings(
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.SUPER_ADMIN)),
) -> list[Setting]:
    return list((await session.scalars(select(Setting).order_by(Setting.key))).all())


@router.patch("", response_model=list[SettingRead])
async def update_settings(
    payload: SettingsPatch,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Setting]:
    existing = {item.key: item for item in (await session.scalars(select(Setting))).all()}
    saved: list[Setting] = []
    now = datetime.now(timezone.utc)
    for key, value in payload.values.items():
        item = existing.get(key)
        if item is None:
            item = Setting(key=key)
            session.add(item)
        item.value = value
        item.updated_by_id = current_user.user_id
        item.updated_at = now
        saved.append(item)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="settings.patch",
        entity_name="settings",
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    for item in saved:
        await session.refresh(item)
    return sorted(saved, key=lambda item: item.key)
