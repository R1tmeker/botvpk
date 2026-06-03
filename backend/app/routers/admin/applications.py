from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import ApplicationStatusHistory, CandidateEvent, JoinApplication, Notification, Squad, User
from ...roles import RoleCode, RoleLevel
from ...schemas.core import (
    ApplicationAcceptRequest,
    ApplicationAdminUpdate,
    CandidateEventCreate,
    CandidateEventRead,
    CandidateEventUpdate,
    JoinApplicationRead,
)
from ...utils.audit import model_snapshot, record_audit, utcnow

router = APIRouter(prefix="/admin/join", tags=["admin:join"])


@router.get("/applications", response_model=list[JoinApplicationRead])
async def applications(
    status_code: str | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[JoinApplication]:
    statement = select(JoinApplication).order_by(JoinApplication.created_at.desc())
    if status_code:
        statement = statement.where(JoinApplication.status_code == status_code)
    return list((await session.scalars(statement)).all())


@router.get("/applications/{application_id}", response_model=JoinApplicationRead)
async def application_detail(
    application_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    application = await session.get(JoinApplication, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return application


@router.patch("/applications/{application_id}", response_model=JoinApplicationRead)
async def update_application(
    application_id: int,
    payload: ApplicationAdminUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    application = await session.get(JoinApplication, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(application, list(updates))
    old_status = application.status_code
    for key, value in updates.items():
        setattr(application, key, value)
    if "status_code" in updates and updates["status_code"] != old_status:
        application.reviewed_by_user_id = current_user.user_id
        application.reviewed_at = utcnow()
        session.add(
            ApplicationStatusHistory(
                application_id=application.id,
                old_status=old_status,
                new_status=application.status_code,
                changed_by_id=current_user.user_id,
                comment=application.admin_comment,
            )
        )
        if updates["status_code"] == "INVITED_NORMATIVES":
            user = await session.scalar(select(User).where(User.telegram_id == application.telegram_id))
            if user:
                session.add(
                    Notification(
                        user_id=user.id,
                        type_code="APPLICATION",
                        title="Приглашение на нормативы",
                        body="Вас приглашают пройти нормативы для вступления в ВПК «Звезда». Ожидайте сообщение от командира.",
                        entity_name="join_applications",
                        entity_id=application.id,
                        send_to_tg=True,
                    )
                )
    application.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="join.application.admin_update",
        entity_name="join_applications",
        entity_id=application.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(application)
    return application


@router.post("/applications/{application_id}/accept", response_model=JoinApplicationRead)
async def accept_application(
    application_id: int,
    payload: ApplicationAcceptRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    application = await session.get(JoinApplication, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    role_code = RoleCode.PARTICIPANT.value
    if payload.squad_id is not None:
        squad = await session.get(Squad, payload.squad_id)
        if squad is None or not squad.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Squad not found or inactive.")
    user = await session.scalar(select(User).where(User.telegram_id == application.telegram_id))
    if user:
        user.full_name = application.full_name
        user.username = application.username
        user.birth_date = application.birth_date
        user.phone = application.phone
        user.squad_id = payload.squad_id
        user.role_code = role_code
        user.status_code = "ACTIVE"
        user.updated_at = utcnow()
    else:
        user = User(
            telegram_id=application.telegram_id,
            username=application.username,
            full_name=application.full_name,
            birth_date=application.birth_date,
            phone=application.phone,
            squad_id=payload.squad_id,
            role_code=role_code,
            status_code="ACTIVE",
            linked_at=utcnow(),
        )
        session.add(user)
        await session.flush()
    old_status = application.status_code
    application.status_code = "ACCEPTED"
    application.accepted_user_id = user.id
    application.admin_comment = payload.admin_comment
    application.reviewed_by_user_id = current_user.user_id
    application.reviewed_at = utcnow()
    application.updated_at = utcnow()
    session.add(
        Notification(
            user_id=user.id,
            type_code="APPLICATION",
            title="Заявка принята",
            body="Поздравляем! Ваша заявка в ВПК «Звезда» принята.",
            entity_name="join_applications",
            entity_id=application.id,
            send_to_tg=True,
        )
    )
    session.add(
        ApplicationStatusHistory(
            application_id=application.id,
            old_status=old_status,
            new_status="ACCEPTED",
            changed_by_id=current_user.user_id,
            comment=payload.admin_comment,
        )
    )
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="join.application.accept",
        entity_name="join_applications",
        entity_id=application.id,
        new_value={**payload.model_dump(mode="json"), "accepted_user_id": user.id, "role_code": role_code},
    )
    await session.commit()
    await session.refresh(application)
    return application


@router.post("/applications/{application_id}/reject", response_model=JoinApplicationRead)
async def reject_application(
    application_id: int,
    payload: ApplicationAdminUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    application = await session.get(JoinApplication, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    updates = payload.model_copy(update={"status_code": "REJECTED"}).model_dump(exclude_unset=False)
    old_status = application.status_code
    for key, value in updates.items():
        setattr(application, key, value)
    application.status_code = "REJECTED"
    application.reviewed_by_user_id = current_user.user_id
    application.reviewed_at = utcnow()
    application.updated_at = utcnow()
    session.add(
        ApplicationStatusHistory(
            application_id=application.id,
            old_status=old_status,
            new_status="REJECTED",
            changed_by_id=current_user.user_id,
            comment=application.admin_comment,
        )
    )
    user = await session.scalar(select(User).where(User.telegram_id == application.telegram_id))
    if user:
        session.add(
            Notification(
                user_id=user.id,
                type_code="APPLICATION",
                title="Заявка отклонена",
                body=application.decision_reason or "Решение по заявке обновлено.",
                entity_name="join_applications",
                entity_id=application.id,
                send_to_tg=True,
            )
        )
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="join.application.reject",
        entity_name="join_applications",
        entity_id=application.id,
        old_value={"status_code": old_status},
        new_value={"status_code": "REJECTED"},
    )
    await session.commit()
    await session.refresh(application)
    return application


@router.get("/events", response_model=list[CandidateEventRead])
async def candidate_events(
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[CandidateEvent]:
    return list((await session.scalars(select(CandidateEvent).order_by(CandidateEvent.start_datetime))).all())


@router.post("/events", response_model=CandidateEventRead, status_code=status.HTTP_201_CREATED)
async def create_candidate_event(
    payload: CandidateEventCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateEvent:
    event = CandidateEvent(created_by_user_id=current_user.user_id or 0, **payload.model_dump())
    session.add(event)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="candidate_event.create",
        entity_name="candidate_events",
        entity_id=event.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/events/{event_id}", response_model=CandidateEventRead)
async def update_candidate_event(
    event_id: int,
    payload: CandidateEventUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> CandidateEvent:
    event = await session.get(CandidateEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate event not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(event, list(updates))
    for key, value in updates.items():
        setattr(event, key, value)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="candidate_event.update",
        entity_name="candidate_events",
        entity_id=event.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(event)
    return event
