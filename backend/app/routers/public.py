from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models import CandidateEvent, LearningCourse, LearningMaterial, PromoBlock
from ..schemas.core import CandidateEventRead, LearningCourseRead, LearningMaterialRead, PromoBlockRead

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/content")
async def public_content(
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    now = datetime.now(timezone.utc)
    promo = list(
        (
            await session.scalars(
                select(PromoBlock)
                .where(PromoBlock.is_active.is_(True))
                .where(PromoBlock.audience_code.in_(("ALL", "NEW_USER", "CANDIDATE")))
                .where((PromoBlock.active_from.is_(None)) | (PromoBlock.active_from <= now))
                .where((PromoBlock.active_to.is_(None)) | (PromoBlock.active_to >= now))
                .order_by(PromoBlock.sort_order, PromoBlock.created_at.desc())
            )
        ).all()
    )
    courses = list(
        (
            await session.scalars(
                select(LearningCourse)
                .where(LearningCourse.is_active.is_(True), LearningCourse.audience_code.in_(("ALL", "CANDIDATE")))
                .order_by(LearningCourse.sort_order)
            )
        ).all()
    )
    materials = list(
        (
            await session.scalars(
                select(LearningMaterial)
                .where(LearningMaterial.is_active.is_(True), LearningMaterial.audience_code.in_(("ALL", "CANDIDATE")))
                .order_by(LearningMaterial.sort_order)
                .limit(20)
            )
        ).all()
    )
    return {
        "title": "ВПК «Звезда»",
        "description": "Подача заявки, подготовка к вступлению и открытые мероприятия.",
        "promo_blocks": [PromoBlockRead.model_validate(item).model_dump(mode="json") for item in promo],
        "courses": [LearningCourseRead.model_validate(item).model_dump(mode="json") for item in courses],
        "materials": [LearningMaterialRead.model_validate(item).model_dump(mode="json") for item in materials],
    }


@router.get("/events", response_model=list[CandidateEventRead])
async def public_events(
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
