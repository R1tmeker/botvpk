from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Appeal, AppealMessage, Notification, User
from ..roles import RoleLevel, role_level
from ..schemas.core import AppealCreate, AppealMessageCreate, AppealMessageRead, AppealRead, AppealUpdate
from ..services.appeal_policy import APPEAL_STATUS_LABELS, can_access_appeal
from ..services.appeals import add_appeal_reply, notify_appeal_commanders, publish_appeal_update
from ..utils.audit import model_snapshot, record_audit, utcnow

router = APIRouter(prefix="/appeals", tags=["appeals"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def can_view_appeal(appeal: Appeal, current_user: CurrentUser) -> bool:
    return can_access_appeal(author_id=appeal.author_user_id, user_id=current_user.user_id, role=current_user.role_level)


async def get_appeal_or_404(session: AsyncSession, appeal_id: int) -> Appeal:
    appeal = await session.get(Appeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found.")
    return appeal


@router.get("", response_model=list[AppealRead])
async def appeals(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Appeal]:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = select(Appeal).order_by(Appeal.created_at.desc())
    else:
        statement = select(Appeal).where(Appeal.author_user_id == current_user.user_id).order_by(Appeal.created_at.desc())
    return list((await session.scalars(statement)).all())


@router.post("", response_model=AppealRead, status_code=status.HTTP_201_CREATED)
async def create_appeal(
    payload: AppealCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    author_id = require_profile(current_user)
    appeal = Appeal(author_user_id=author_id, **payload.model_dump())
    session.add(appeal)
    await session.flush()
    session.add(AppealMessage(appeal_id=appeal.id, author_id=author_id, body=payload.description))
    await record_audit(
        session,
        user_id=author_id,
        action_code="appeal.create",
        entity_name="appeals",
        entity_id=appeal.id,
        new_value=payload.model_dump(mode="json"),
    )
    author_user = await session.get(User, author_id)
    body = f"Тема: {appeal.subject}"
    if not payload.is_anonymous and author_user is not None:
        body = f"{author_user.full_name}: {body}"
    await notify_appeal_commanders(session, appeal, sender_id=author_id, title="Новое обращение", body=body)
    await session.commit()
    await session.refresh(appeal)
    await publish_appeal_update()
    return appeal


@router.get("/{appeal_id}", response_model=AppealRead)
async def appeal_detail(
    appeal_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    appeal = await get_appeal_or_404(session, appeal_id)
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this appeal.")
    return appeal


@router.patch("/{appeal_id}", response_model=AppealRead)
async def update_appeal(
    appeal_id: int,
    payload: AppealUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Appeal:
    user_id = require_profile(current_user)
    appeal = await session.scalar(select(Appeal).where(Appeal.id == appeal_id).with_for_update())
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found.")
    updates = payload.model_dump(exclude_unset=True)
    assignee_id = updates.get("assignee_user_id")
    if assignee_id is not None:
        assignee = await session.get(User, assignee_id)
        if assignee is None or assignee.status_code != "ACTIVE" or role_level(assignee.role_code) < RoleLevel.DEPUTY_PLATOON_COMMANDER:
            raise HTTPException(status_code=422, detail="Ответственным может быть только активный участник командования взвода.")
    old = model_snapshot(appeal, list(updates))
    for key, value in updates.items():
        setattr(appeal, key, value)
    appeal.updated_at = utcnow()
    if appeal.status_code in {"CLOSED", "RESOLVED"} and appeal.closed_at is None:
        appeal.closed_at = utcnow()
    elif appeal.status_code not in {"CLOSED", "RESOLVED"}:
        appeal.closed_at = None
    if "status_code" in updates and old.get("status_code") != appeal.status_code and appeal.author_user_id is not None and appeal.author_user_id != user_id:
        session.add(Notification(
            user_id=appeal.author_user_id, type_code="APPEAL", category_code="APPEALS",
            title="Изменился статус обращения", body=f"«{appeal.subject}»: {APPEAL_STATUS_LABELS[appeal.status_code]}",
            entity_name="appeals", entity_id=appeal.id, deep_link=f"/appeals?id={appeal.id}", send_to_tg=True,
        ))
    await record_audit(
        session,
        user_id=user_id,
        action_code="appeal.update",
        entity_name="appeals",
        entity_id=appeal.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(appeal)
    await publish_appeal_update()
    return appeal


@router.get("/{appeal_id}/messages", response_model=list[AppealMessageRead])
async def appeal_messages(
    appeal_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[AppealMessage]:
    appeal = await get_appeal_or_404(session, appeal_id)
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this appeal.")
    statement = select(AppealMessage).where(AppealMessage.appeal_id == appeal_id).order_by(AppealMessage.created_at, AppealMessage.id)
    return list((await session.scalars(statement)).all())


@router.post("/{appeal_id}/messages", response_model=AppealMessageRead, status_code=status.HTTP_201_CREATED)
async def create_appeal_message(
    appeal_id: int,
    payload: AppealMessageCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> AppealMessage:
    user_id = require_profile(current_user)
    appeal = await session.scalar(select(Appeal).where(Appeal.id == appeal_id).with_for_update())
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found.")
    if not can_view_appeal(appeal, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot write to this appeal.")
    message = await add_appeal_reply(session, appeal, sender_id=user_id, role=current_user.role_level, body=payload.body)
    await session.commit()
    await session.refresh(message)
    await publish_appeal_update()
    return message
