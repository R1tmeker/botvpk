from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import Normative, NormativeSubmission, User
from ..roles import RoleLevel
from ..schemas.core import (
    MessageResponse,
    NormativeCreate,
    NormativeRead,
    NormativeReviewRequest,
    NormativeSubmissionRead,
    NormativeSubmitRequest,
    NormativeUpdate,
)
from ..utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/normatives", tags=["normatives"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def normative_visible(normative: Normative, current_user: CurrentUser) -> bool:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return True
    if not normative.is_active:
        return False
    if normative.squad_id is not None and normative.squad_id != current_user.squad_id:
        return False
    if normative.target_audience in {"ALL", current_user.role_code}:
        return True
    if normative.target_audience == "SQUAD" and normative.squad_id == current_user.squad_id:
        return True
    if normative.target_audience == "COMMANDERS":
        return current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER
    return normative.target_audience == "PARTICIPANTS" and current_user.role_level >= RoleLevel.PARTICIPANT


async def get_normative_or_404(session: AsyncSession, normative_id: int) -> Normative:
    normative = await session.get(Normative, normative_id)
    if normative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Normative not found.")
    return normative


@router.get("", response_model=list[NormativeRead])
async def list_normatives(
    active_only: bool = True,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Normative]:
    statement = select(Normative).order_by(Normative.deadline_at.nullslast(), Normative.created_at.desc())
    if active_only:
        statement = statement.where(Normative.is_active.is_(True))
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where((Normative.squad_id.is_(None)) | (Normative.squad_id == current_user.squad_id))
    items = list((await session.scalars(statement)).all())
    return [item for item in items if normative_visible(item, current_user)]


@router.get("/submissions/my", response_model=list[NormativeSubmissionRead])
async def my_submissions(
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NormativeSubmission]:
    user_id = require_profile(current_user)
    statement = (
        select(NormativeSubmission)
        .where(NormativeSubmission.user_id == user_id)
        .order_by(NormativeSubmission.submitted_at.desc())
    )
    return list((await session.scalars(statement)).all())


@router.get("/submissions/pending", response_model=list[NormativeSubmissionRead])
async def pending_submissions(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NormativeSubmission]:
    statement = (
        select(NormativeSubmission)
        .join(User, User.id == NormativeSubmission.user_id)
        .where(NormativeSubmission.status_code.in_(("SUBMITTED", "PENDING_REVIEW", "PENDING")))
        .order_by(NormativeSubmission.submitted_at.desc())
    )
    if squad_id is not None:
        if not can_manage_squad(current_user, squad_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this squad.")
        statement = statement.where(User.squad_id == squad_id)
    elif current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where(User.squad_id == current_user.squad_id)
    return list((await session.scalars(statement)).all())


@router.patch("/submissions/{submission_id}/review", response_model=NormativeSubmissionRead)
async def review_submission(
    submission_id: int,
    payload: NormativeReviewRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> NormativeSubmission:
    reviewer_id = require_profile(current_user)
    submission = await session.get(NormativeSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")
    submitter = await session.get(User, submission.user_id)
    if submitter is None or not can_manage_squad(current_user, submitter.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot review this submission.")
    old = model_snapshot(submission, ["status_code", "reviewer_comment", "grade_value", "reviewed_by_id", "reviewed_at"])
    submission.status_code = payload.status_code
    submission.reviewer_comment = payload.reviewer_comment
    submission.grade_value = payload.grade_value
    submission.reviewed_by_id = reviewer_id
    submission.reviewed_at = utcnow()
    submission.updated_at = utcnow()
    await record_audit(
        session,
        user_id=reviewer_id,
        action_code="normative_submission.review",
        entity_name="normative_submissions",
        entity_id=submission.id,
        old_value=old,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(submission)
    return submission


@router.get("/{normative_id}", response_model=NormativeRead)
async def normative_detail(
    normative_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    normative = await get_normative_or_404(session, normative_id)
    if not normative_visible(normative, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this normative.")
    return normative


@router.post("/{normative_id}/submit", response_model=NormativeSubmissionRead)
async def submit_normative(
    normative_id: int,
    payload: NormativeSubmitRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> NormativeSubmission:
    user_id = require_profile(current_user)
    normative = await get_normative_or_404(session, normative_id)
    if not normative_visible(normative, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit this normative.")
    submission = await session.scalar(
        select(NormativeSubmission).where(
            NormativeSubmission.normative_id == normative_id,
            NormativeSubmission.user_id == user_id,
        )
    )
    if submission is None:
        submission = NormativeSubmission(normative_id=normative_id, user_id=user_id)
        session.add(submission)
    old = model_snapshot(submission, ["status_code", "file_id", "comment"]) if submission.id else None
    submission.status_code = "SUBMITTED"
    submission.file_id = payload.file_id
    submission.comment = payload.comment
    submission.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        action_code="normative_submission.submit",
        entity_name="normative_submissions",
        entity_id=submission.id,
        old_value=old,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(submission)
    return submission


@router.post("", response_model=NormativeRead, status_code=status.HTTP_201_CREATED)
async def create_normative(
    payload: NormativeCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    creator_id = require_profile(current_user)
    normative = Normative(created_by_user_id=creator_id, **payload.model_dump())
    session.add(normative)
    await session.flush()
    await record_audit(
        session,
        user_id=creator_id,
        action_code="normative.create",
        entity_name="normatives",
        entity_id=normative.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(normative)
    return normative


@router.patch("/{normative_id}", response_model=NormativeRead)
async def update_normative(
    normative_id: int,
    payload: NormativeUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    user_id = require_profile(current_user)
    normative = await get_normative_or_404(session, normative_id)
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(normative, list(updates))
    for key, value in updates.items():
        setattr(normative, key, value)
    normative.updated_at = utcnow()
    await record_audit(
        session,
        user_id=user_id,
        action_code="normative.update",
        entity_name="normatives",
        entity_id=normative.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(normative)
    return normative


@router.delete("/{normative_id}", response_model=MessageResponse)
async def delete_normative(
    normative_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    normative = await get_normative_or_404(session, normative_id)
    normative.is_active = False
    normative.updated_at = utcnow()
    await record_audit(
        session,
        user_id=user_id,
        action_code="normative.archive",
        entity_name="normatives",
        entity_id=normative.id,
        old_value={"is_active": True},
        new_value={"is_active": False},
    )
    await session.commit()
    return MessageResponse(detail="Normative archived.")
