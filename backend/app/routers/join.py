from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import CandidateEvent, CandidateEventResponse, JoinApplication, User
from ..roles import RoleCode
from ..schemas.core import (
    CandidateEventRead,
    CandidateEventResponseCreate,
    JoinApplicationCreate,
    JoinApplicationRead,
    JoinApplicationUpdate,
    MessageResponse,
)
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/join", tags=["join"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/applications", response_model=JoinApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: JoinApplicationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    if not payload.consent_given:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required.")
    existing = await session.scalar(
        select(JoinApplication)
        .where(
            JoinApplication.telegram_id == current_user.telegram_id,
            JoinApplication.status_code.not_in(["REJECTED", "ARCHIVED", "ACCEPTED"]),
        )
        .order_by(JoinApplication.id.desc())
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active application already exists.")
    application = JoinApplication(
        telegram_id=current_user.telegram_id,
        username=current_user.user.username if current_user.user else None,
        **payload.model_dump(),
    )
    session.add(application)
    await session.flush()
    user = current_user.user or await session.scalar(select(User).where(User.telegram_id == current_user.telegram_id))
    if user is None:
        user = User(
            telegram_id=current_user.telegram_id,
            username=application.username,
            full_name=payload.full_name,
            birth_date=payload.birth_date,
            phone=payload.phone,
            role_code=RoleCode.CANDIDATE.value,
            status_code="ACTIVE",
        )
        session.add(user)
    elif user.role_code == RoleCode.PUBLIC_USER.value:
        user.full_name = payload.full_name
        user.birth_date = payload.birth_date
        user.phone = payload.phone
        user.role_code = RoleCode.CANDIDATE.value
        user.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="join.application.create",
        entity_name="join_applications",
        entity_id=application.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(application)
    return application


@router.get("/me", response_model=JoinApplicationRead | None)
async def my_application(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication | None:
    return await session.scalar(
        select(JoinApplication)
        .where(JoinApplication.telegram_id == current_user.telegram_id)
        .order_by(JoinApplication.id.desc())
    )


@router.patch("/me", response_model=JoinApplicationRead)
async def update_my_application(
    payload: JoinApplicationUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JoinApplication:
    application = await session.scalar(
        select(JoinApplication)
        .where(JoinApplication.telegram_id == current_user.telegram_id)
        .order_by(JoinApplication.id.desc())
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    if application.status_code in {"ACCEPTED", "REJECTED", "ARCHIVED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is already closed.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(application, list(updates))
    for key, value in updates.items():
        setattr(application, key, value)
    application.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="join.application.update_self",
        entity_name="join_applications",
        entity_id=application.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(application)
    return application


@router.get("/events", response_model=list[CandidateEventRead])
async def candidate_events(
    session: AsyncSession = Depends(get_db_session),
) -> list[CandidateEvent]:
    return list(
        (
            await session.scalars(
                select(CandidateEvent)
                .where(CandidateEvent.is_active.is_(True))
                .order_by(CandidateEvent.start_datetime)
            )
        ).all()
    )


@router.post("/events/{event_id}/respond", response_model=MessageResponse)
async def respond_candidate_event(
    event_id: int,
    payload: CandidateEventResponseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    application = await session.scalar(
        select(JoinApplication)
        .where(JoinApplication.telegram_id == current_user.telegram_id)
        .order_by(JoinApplication.id.desc())
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    event = await session.get(CandidateEvent, event_id)
    if not event or not event.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate event not found.")
    response = await session.scalar(
        select(CandidateEventResponse).where(
            CandidateEventResponse.application_id == application.id,
            CandidateEventResponse.event_id == event_id,
        )
    )
    if response:
        response.response_code = payload.response_code
        response.comment = payload.comment
        response.responded_at = utcnow()
    else:
        session.add(
            CandidateEventResponse(
                application_id=application.id,
                event_id=event_id,
                response_code=payload.response_code,
                comment=payload.comment,
            )
        )
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="candidate_event.respond",
        entity_name="candidate_events",
        entity_id=event_id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return MessageResponse(detail="Response saved.")
