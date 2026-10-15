from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import Normative, NormativeSubmission, NormativeSubmissionFile, Notification, User
from ..roles import CONFIRMED_ROLES, RoleLevel
from ..services.normative_cycles import attach_period, monday_in_club, normative_period
from ..services.normative_progress import progress_for_users
from ..schemas.core import (
    MessageResponse,
    NormativeCreate,
    NormativeRead,
    NormativeReviewRequest,
    NormativeSubmissionRead,
    NormativeSubmitRequest,
    NormativeUpdate,
)
from ..services.normatives import submit_normative as submit_normative_service
from ..utils.audit import model_snapshot, record_audit, utcnow

router = APIRouter(prefix="/normatives", tags=["normatives"])


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
    if current_user.role_level < RoleLevel.CANDIDATE and normative.target_audience == "CANDIDATE":
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


async def attach_submission_files(
    session: AsyncSession, submissions: list[NormativeSubmission]
) -> list[NormativeSubmission]:
    submission_ids = [item.id for item in submissions if item.id is not None]
    if not submission_ids:
        return submissions
    rows = (
        await session.execute(
            select(NormativeSubmissionFile.submission_id, NormativeSubmissionFile.file_id)
            .where(NormativeSubmissionFile.submission_id.in_(submission_ids))
            .order_by(NormativeSubmissionFile.id)
        )
    ).all()
    by_submission: dict[int, list[int]] = {}
    for submission_id, file_id in rows:
        by_submission.setdefault(submission_id, []).append(file_id)
    for submission in submissions:
        ids = by_submission.get(submission.id, [])
        if not ids and submission.file_id is not None:
            ids = [submission.file_id]
        submission.file_ids = ids
    return submissions


async def attach_submission_context(
    session: AsyncSession, submissions: list[NormativeSubmission]
) -> list[NormativeSubmission]:
    await attach_submission_files(session, submissions)
    if not submissions:
        return submissions

    user_ids = {item.user_id for item in submissions}
    reviewer_ids = {item.reviewed_by_id for item in submissions if item.reviewed_by_id is not None}
    normative_ids = {item.normative_id for item in submissions}

    user_rows = (
        await session.execute(select(User.id, User.full_name).where(User.id.in_(user_ids | reviewer_ids)))
    ).all()
    user_names = {user_id: full_name for user_id, full_name in user_rows}

    normative_rows = (
        await session.execute(select(Normative.id, Normative.title).where(Normative.id.in_(normative_ids)))
    ).all()
    normative_titles = {normative_id: title for normative_id, title in normative_rows}

    for submission in submissions:
        submission.user_full_name = user_names.get(submission.user_id)
        submission.normative_title = normative_titles.get(submission.normative_id)
        submission.reviewer_full_name = user_names.get(submission.reviewed_by_id) if submission.reviewed_by_id else None
    return submissions


@router.get("", response_model=list[NormativeRead])
async def list_normatives(
    active_only: bool = True,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[Normative]:
    statement = select(Normative).order_by(Normative.deadline_at.nullslast(), Normative.created_at.desc())
    if active_only:
        statement = statement.where(Normative.is_active.is_(True))
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where((Normative.squad_id.is_(None)) | (Normative.squad_id == current_user.squad_id))
    items = list((await session.scalars(statement)).all())
    return [attach_period(item) for item in items if normative_visible(item, current_user)]


@router.get("/progress/my")
async def my_normative_progress(
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await session.get(User, require_profile(current_user))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return (await progress_for_users(session, [user]))[0]


@router.get("/progress/roster")
async def roster_normative_progress(
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    statement = (
        select(User)
        .where(User.status_code == "ACTIVE", User.role_code.in_((*CONFIRMED_ROLES, "CANDIDATE")))
        .order_by(User.full_name)
    )
    if current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        if current_user.squad_id is None:
            return []
        statement = statement.where(User.squad_id == current_user.squad_id)
    return await progress_for_users(session, list((await session.scalars(statement)).all()))


@router.get("/submissions/my", response_model=list[NormativeSubmissionRead])
async def my_submissions(
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NormativeSubmission]:
    user_id = require_profile(current_user)
    statement = (
        select(NormativeSubmission)
        .where(NormativeSubmission.user_id == user_id)
        .order_by(NormativeSubmission.submitted_at.desc())
        .offset(max(0, offset))
        .limit(min(max(1, limit), 500))
    )
    return await attach_submission_context(session, list((await session.scalars(statement)).all()))


@router.get("/submissions/pending", response_model=list[NormativeSubmissionRead])
async def pending_submissions(
    squad_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
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
    statement = statement.offset(max(0, offset)).limit(min(max(1, limit), 500))
    return await attach_submission_context(session, list((await session.scalars(statement)).all()))


@router.get("/submissions/history", response_model=list[NormativeSubmissionRead])
async def submission_history(
    status_code: str | None = None,
    squad_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[NormativeSubmission]:
    statement = (
        select(NormativeSubmission)
        .join(User, User.id == NormativeSubmission.user_id)
        .order_by(NormativeSubmission.submitted_at.desc())
    )
    if status_code and status_code.upper() != "ALL":
        codes = [item.strip().upper() for item in status_code.split(",") if item.strip()]
        if codes:
            statement = statement.where(NormativeSubmission.status_code.in_(codes))
    if squad_id is not None:
        if not can_manage_squad(current_user, squad_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this squad.")
        statement = statement.where(User.squad_id == squad_id)
    elif current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where(User.squad_id == current_user.squad_id)
    statement = statement.offset(max(0, offset)).limit(min(max(1, limit), 500))
    return await attach_submission_context(session, list((await session.scalars(statement)).all()))


@router.patch("/submissions/{submission_id}/review", response_model=NormativeSubmissionRead)
async def review_submission(
    submission_id: int,
    payload: NormativeReviewRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> NormativeSubmission:
    reviewer_id = require_profile(current_user)
    submission = await session.get(NormativeSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")
    submitter = await session.get(User, submission.user_id)
    if submitter is None or not can_manage_squad(current_user, submitter.squad_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot review this submission.")
    old = model_snapshot(
        submission, ["status_code", "reviewer_comment", "grade_value", "reviewed_by_id", "reviewed_at"]
    )
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
    normative = await session.get(Normative, submission.normative_id)
    norm_title = normative.title if normative else f"норматив #{submission.normative_id}"
    status_labels = {
        "ACCEPTED": ("Принято", "Ваша сдача принята!"),
        "REJECTED": ("Отклонено", "Ваша сдача отклонена."),
        "NEEDS_REDO": ("На доработку", "Требуется пересдача."),
    }
    status_title, status_body = status_labels.get(payload.status_code, ("Статус обновлён", "Статус сдачи изменён."))
    body_parts = [f"Норматив: «{norm_title}»", status_body]
    if payload.reviewer_comment:
        body_parts.append(f"Комментарий: {payload.reviewer_comment}")
    if payload.grade_value:
        body_parts.append(f"Оценка: {payload.grade_value}")
    session.add(
        Notification(
            user_id=submission.user_id,
            type_code="NORMATIVE",
            title=f"{status_title}: {norm_title}",
            body="\n".join(body_parts),
            entity_name="normative_submissions",
            entity_id=submission.id,
            send_to_tg=True,
        )
    )
    await session.commit()
    await session.refresh(submission)
    await attach_submission_context(session, [submission])
    return submission


@router.get("/{normative_id}", response_model=NormativeRead)
async def normative_detail(
    normative_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    normative = await get_normative_or_404(session, normative_id)
    if not normative_visible(normative, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view this normative.")
    return attach_period(normative)


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
    submitter = await session.get(User, user_id)
    if submitter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    file_ids = (
        payload.file_ids if payload.file_ids is not None else ([] if payload.file_id is None else [payload.file_id])
    )
    file_ids = list(dict.fromkeys(file_ids))
    if not attach_period(normative).is_submission_open:
        raise HTTPException(status_code=409, detail="Сдача этого норматива ещё не открыта.")
    if normative.recurrence_days and payload.period_start_date != normative_period(normative).start:
        raise HTTPException(
            status_code=409, detail="Началась новая неделя. Обновите норматив и отправьте работу для текущего периода."
        )
    try:
        submission = await submit_normative_service(
            session,
            normative=normative,
            submitter=submitter,
            status_code="SUBMITTED",
            comment=payload.comment,
            file_ids=file_ids,
            audit_action_code="normative_submission.submit",
            audit_value=payload.model_dump(mode="json"),
            expected_period_start=payload.period_start_date,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(submission)
    await attach_submission_context(session, [submission])
    return submission


@router.post("", response_model=NormativeRead, status_code=status.HTTP_201_CREATED)
async def create_normative(
    payload: NormativeCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    creator_id = require_profile(current_user)
    normative = Normative(created_by_user_id=creator_id, **payload.model_dump())
    if normative.recurrence_days and normative.recurrence_start_date is None:
        normative.recurrence_start_date = monday_in_club()
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
    return attach_period(normative)


@router.patch("/{normative_id}", response_model=NormativeRead)
async def update_normative(
    normative_id: int,
    payload: NormativeUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> Normative:
    user_id = require_profile(current_user)
    normative = await session.scalar(
        select(Normative)
        .where(Normative.id == normative_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if normative is None:
        raise HTTPException(status_code=404, detail="Normative not found.")
    updates = payload.model_dump(exclude_unset=True)
    enabling_weekly = not normative.recurrence_days and updates.get("recurrence_days") == 7
    old = model_snapshot(normative, list(updates))
    for key, value in updates.items():
        setattr(normative, key, value)
    if normative.recurrence_days and normative.recurrence_start_date is None:
        normative.recurrence_start_date = monday_in_club()
    if enabling_weekly:
        submissions = list(
            (
                await session.scalars(
                    select(NormativeSubmission)
                    .where(
                        NormativeSubmission.normative_id == normative.id,
                    )
                    .order_by(NormativeSubmission.submitted_at.desc(), NormativeSubmission.id.desc())
                )
            ).all()
        )
        occupied = {(item.user_id, item.period_start_date) for item in submissions if item.period_start_date}
        for submission in submissions:
            period_start = monday_in_club(submission.submitted_at)
            if submission.period_start_date is not None or (submission.user_id, period_start) in occupied:
                continue
            submission.period_start_date = period_start
            submission.period_end_date = submission.period_start_date + timedelta(days=7)
            occupied.add((submission.user_id, period_start))
    normative.updated_at = utcnow()
    await record_audit(
        session,
        user_id=user_id,
        action_code="normative.update",
        entity_name="normatives",
        entity_id=normative.id,
        old_value=old,
        new_value=payload.model_dump(exclude_unset=True, mode="json"),
    )
    await session.commit()
    await session.refresh(normative)
    return attach_period(normative)


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
