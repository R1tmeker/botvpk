from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import PromoBlock
from ...roles import RoleLevel
from ...schemas.core import MessageResponse, PromoBlockCreate, PromoBlockRead, PromoBlockUpdate
from ...utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/admin/promo", tags=["admin:promo"])


@router.get("", response_model=list[PromoBlockRead])
async def promo_blocks(
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
) -> list[PromoBlock]:
    statement = select(PromoBlock).order_by(PromoBlock.sort_order, PromoBlock.created_at.desc())
    return list((await session.scalars(statement)).all())


@router.post("", response_model=PromoBlockRead, status_code=status.HTTP_201_CREATED)
async def create_promo_block(
    payload: PromoBlockCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> PromoBlock:
    item = PromoBlock(created_by_id=current_user.user_id, **payload.model_dump())
    session.add(item)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="promo_block.create",
        entity_name="promo_blocks",
        entity_id=item.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/{promo_id}", response_model=PromoBlockRead)
async def update_promo_block(
    promo_id: int,
    payload: PromoBlockUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> PromoBlock:
    item = await session.get(PromoBlock, promo_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo block not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(item, list(updates))
    for key, value in updates.items():
        setattr(item, key, value)
    item.updated_at = datetime.now(timezone.utc)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="promo_block.update",
        entity_name="promo_blocks",
        entity_id=item.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{promo_id}", response_model=MessageResponse)
async def delete_promo_block(
    promo_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    item = await session.get(PromoBlock, promo_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo block not found.")
    old = model_snapshot(
        item,
        [
            "title",
            "body",
            "button_text",
            "button_url",
            "action_type_code",
            "audience_code",
            "style_code",
            "sort_order",
            "is_active",
            "active_from",
            "active_to",
        ],
    )
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="promo_block.delete",
        entity_name="promo_blocks",
        entity_id=item.id,
        old_value=old,
        new_value=None,
    )
    await session.delete(item)
    await session.commit()
    return MessageResponse(detail="Promo block deleted.")
