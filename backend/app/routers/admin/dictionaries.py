from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import AbsenceReason
from ...roles import RoleLevel
from ...schemas.core import AbsenceReasonRead, AbsenceReasonUpdate
from ...utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/admin/dictionaries", tags=["admin:dictionaries"])


@router.get("", response_model=dict[str, list[AbsenceReasonRead]])
async def dictionaries(
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
) -> dict[str, list[AbsenceReason]]:
    reasons = list((await session.scalars(select(AbsenceReason).order_by(AbsenceReason.sort_order))).all())
    return {"absence_reasons": reasons}


@router.patch("/{table}/{item_id}", response_model=AbsenceReasonRead)
async def update_dictionary_item(
    table: str,
    item_id: int,
    payload: AbsenceReasonUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> AbsenceReason:
    if table != "absence_reasons":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dictionary table not found.")
    item = await session.get(AbsenceReason, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dictionary item not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(item, list(updates))
    for key, value in updates.items():
        setattr(item, key, value)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="dictionary.update",
        entity_name=table,
        entity_id=item.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(item)
    return item
