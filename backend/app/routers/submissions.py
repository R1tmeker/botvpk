from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..roles import RoleLevel
from ..schemas.core import NormativeReviewRequest, NormativeSubmissionRead
from .normatives import my_submissions as list_my_normative_submissions
from .normatives import pending_submissions as list_pending_normative_submissions
from .normatives import review_submission as review_normative_submission
from .normatives import submission_history as list_normative_submission_history

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("/my", response_model=list[NormativeSubmissionRead])
async def my_submissions(
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await list_my_normative_submissions(limit=limit, offset=offset, current_user=current_user, session=session)


@router.get("/pending", response_model=list[NormativeSubmissionRead])
async def pending_submissions(
    squad_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
):
    return await list_pending_normative_submissions(
        squad_id=squad_id,
        limit=limit,
        offset=offset,
        current_user=current_user,
        session=session,
    )


@router.get("/history", response_model=list[NormativeSubmissionRead])
async def submission_history(
    status_code: str | None = None,
    squad_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
):
    return await list_normative_submission_history(
        status_code=status_code,
        squad_id=squad_id,
        limit=limit,
        offset=offset,
        current_user=current_user,
        session=session,
    )


@router.patch("/{submission_id}/review", response_model=NormativeSubmissionRead)
async def review_submission(
    submission_id: int,
    payload: NormativeReviewRequest,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
):
    return await review_normative_submission(submission_id, payload, current_user, session)
