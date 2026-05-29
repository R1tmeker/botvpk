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


async def clear_user_lead_refs(
    session: AsyncSession,
    user_id: int,
    *,
    keep_squad_id: int | None = None,
    keep_field: str | None = None,
) -> None:
    rows = list(
        (
            await session.scalars(
                select(Squad).where(
                    (Squad.commander_user_id == user_id) | (Squad.deputy_user_id == user_id)
                )
            )
        ).all()
    )
    for row in rows:
        if row.commander_user_id == user_id and not (row.id == keep_squad_id and keep_field == "commander_user_id"):
            row.commander_user_id = None
        if row.deputy_user_id == user_id and not (row.id == keep_squad_id and keep_field == "deputy_user_id"):
            row.deputy_user_id = None


async def demote_old_lead(session: AsyncSession, user_id: int | None, role_code: str, replacement_id: int | None) -> None:
    if user_id is None or user_id == replacement_id:
        return
    user = await session.get(User, user_id)
    if user is not None and user.role_code == role_code:
        user.role_code = "PARTICIPANT"


async def apply_squad_lead_roles(
    session: AsyncSession,
    squad: Squad,
    updates: dict,
    old_commander_id: int | None,
    old_deputy_id: int | None,
) -> None:
    commander_id = updates.get("commander_user_id") if "commander_user_id" in updates else squad.commander_user_id
    deputy_id = updates.get("deputy_user_id") if "deputy_user_id" in updates else squad.deputy_user_id
    if commander_id is not None and deputy_id is not None and commander_id == deputy_id:
        if "commander_user_id" in updates and "deputy_user_id" not in updates:
            squad.deputy_user_id = None
            deputy_id = None
        elif "deputy_user_id" in updates and "commander_user_id" not in updates:
            squad.commander_user_id = None
            commander_id = None
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Commander and deputy must be different users.",
            )
    if "commander_user_id" in updates:
        await demote_old_lead(session, old_commander_id, "SQUAD_COMMANDER", commander_id)
    if "commander_user_id" in updates and commander_id is not None:
        commander = await session.get(User, commander_id)
        if commander is None or commander.status_code == "ARCHIVED":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commander user not found.")
        await clear_user_lead_refs(session, commander.id, keep_squad_id=squad.id, keep_field="commander_user_id")
        commander.squad_id = squad.id
        commander.role_code = "SQUAD_COMMANDER"
        squad.commander_user_id = commander.id
    if "deputy_user_id" in updates:
        await demote_old_lead(session, old_deputy_id, "DEPUTY_SQUAD_COMMANDER", deputy_id)
    if "deputy_user_id" in updates and deputy_id is not None:
        deputy = await session.get(User, deputy_id)
        if deputy is None or deputy.status_code == "ARCHIVED":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deputy user not found.")
        await clear_user_lead_refs(session, deputy.id, keep_squad_id=squad.id, keep_field="deputy_user_id")
        deputy.squad_id = squad.id
        deputy.role_code = "DEPUTY_SQUAD_COMMANDER"
        squad.deputy_user_id = deputy.id


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
    old_commander_id = squad.commander_user_id
    old_deputy_id = squad.deputy_user_id
    for key, value in updates.items():
        setattr(squad, key, value)
    await apply_squad_lead_roles(session, squad, updates, old_commander_id, old_deputy_id)
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
