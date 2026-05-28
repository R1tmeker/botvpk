from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import MenuCard
from ...roles import RoleLevel
from ...schemas.core import MenuCardCreate, MenuCardRead, MenuCardUpdate
from ...utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/admin/menu", tags=["admin:menu"])


@router.get("", response_model=list[MenuCardRead])
async def menu_cards(
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
) -> list[MenuCard]:
    statement = select(MenuCard).order_by(MenuCard.sort_order, MenuCard.title)
    return list((await session.scalars(statement)).all())


@router.post("", response_model=MenuCardRead, status_code=status.HTTP_201_CREATED)
async def create_menu_card(
    payload: MenuCardCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> MenuCard:
    card = MenuCard(**payload.model_dump())
    session.add(card)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="menu_card.create",
        entity_name="menu_cards",
        entity_id=card.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(card)
    return card


@router.patch("/{card_id}", response_model=MenuCardRead)
async def update_menu_card(
    card_id: int,
    payload: MenuCardUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> MenuCard:
    card = await session.get(MenuCard, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu card not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(card, list(updates))
    for key, value in updates.items():
        setattr(card, key, value)
    card.updated_at = datetime.now(timezone.utc)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="menu_card.update",
        entity_name="menu_cards",
        entity_id=card.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(card)
    return card
