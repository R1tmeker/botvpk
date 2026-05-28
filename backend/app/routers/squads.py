from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Squad, User
from ..roles import RoleLevel
from ..schemas.core import SquadCreate, SquadRead, SquadUpdate, UserRead
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/squads", tags=["squads"])


@router.get("/my", response_model=dict)
async def my_squad(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if current_user.squad_id is None:
        return {"squad": None, "members": []}
    squad = await session.get(Squad, current_user.squad_id)
    members = list(
        (
            await session.scalars(
                select(User)
                .where(User.squad_id == current_user.squad_id, User.status_code == "ACTIVE")
                .order_by(User.full_name)
            )
        ).all()
    )
    return {
        "squad": SquadRead.model_validate(squad).model_dump(mode="json") if squad else None,
        "members": [UserRead.model_validate(member).model_dump(mode="json") for member in members],
    }


@router.get("", response_model=list[SquadRead])
async def squads(
    include_inactive: bool = False,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Squad]:
    statement = select(Squad).order_by(Squad.name)
    if not include_inactive:
        statement = statement.where(Squad.is_active.is_(True))
    return list((await session.scalars(statement)).all())


@router.post("", response_model=SquadRead, status_code=status.HTTP_201_CREATED)
async def create_squad(
    payload: SquadCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Squad:
    squad = Squad(**payload.model_dump())
    session.add(squad)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="squad.create",
        entity_name="squads",
        entity_id=squad.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(squad)
    return squad


@router.patch("/{squad_id}", response_model=SquadRead)
async def update_squad(
    squad_id: int,
    payload: SquadUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Squad:
    squad = await session.get(Squad, squad_id)
    if not squad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Squad not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(squad, list(updates))
    for key, value in updates.items():
        setattr(squad, key, value)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="squad.update",
        entity_name="squads",
        entity_id=squad.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(squad)
    return squad
