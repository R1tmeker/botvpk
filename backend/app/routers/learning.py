from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import LearningCourse, LearningMaterial, LearningProgress
from ..roles import RoleLevel
from ..schemas.core import LearningCourseRead, LearningMaterialRead, MessageResponse
from ..services.audiences import visible_audiences

router = APIRouter(prefix="/learning", tags=["learning"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def audience_visible(audience_code: str, current_user: CurrentUser) -> bool:
    return audience_code in visible_audiences(current_user.role_code, current_user.role_level)


@router.get("/materials", response_model=list[LearningMaterialRead])
async def learning_materials(
    course_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[LearningMaterialRead]:
    statement = (
        select(LearningMaterial)
        .where(LearningMaterial.is_active.is_(True), LearningMaterial.audience_code.in_(visible_audiences(current_user.role_code, current_user.role_level)))
        .order_by(LearningMaterial.sort_order, LearningMaterial.created_at.desc())
    )
    if course_id is not None:
        statement = statement.where(LearningMaterial.course_id == course_id)
    items = list((await session.scalars(statement)).all())
    progress = {}
    if current_user.user_id is not None and items:
        rows = (await session.scalars(select(LearningProgress).where(
            LearningProgress.user_id == current_user.user_id,
            LearningProgress.material_id.in_([item.id for item in items]),
        ))).all()
        progress = {row.material_id: row.viewed_at for row in rows}
    return [LearningMaterialRead.model_validate(item).model_copy(update={
        "is_viewed": item.id in progress, "viewed_at": progress.get(item.id),
    }) for item in items]


@router.get("/courses", response_model=list[LearningCourseRead])
async def learning_courses(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[LearningCourse]:
    statement = (
        select(LearningCourse)
        .where(LearningCourse.is_active.is_(True))
        .order_by(LearningCourse.sort_order, LearningCourse.created_at.desc())
    )
    items = list((await session.scalars(statement)).all())
    return [item for item in items if audience_visible(item.audience_code, current_user)]


@router.get("/courses/{course_id}", response_model=dict)
async def learning_course_detail(
    course_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PUBLIC_USER)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    course = await session.get(LearningCourse, course_id)
    if course is None or not course.is_active or not audience_visible(course.audience_code, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    materials = await learning_materials(course_id, current_user, session)
    return {
        "course": LearningCourseRead.model_validate(course).model_dump(mode="json"),
        "materials": [LearningMaterialRead.model_validate(item).model_dump(mode="json") for item in materials],
    }


@router.post("/materials/{material_id}/view", response_model=MessageResponse)
async def mark_material_viewed(
    material_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    material = await session.get(LearningMaterial, material_id)
    if material is None or not material.is_active or not audience_visible(material.audience_code, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    # Concurrent taps and retries keep the first completion time and never violate the unique key.
    await session.execute(insert(LearningProgress).values(user_id=user_id, material_id=material_id)
                          .on_conflict_do_nothing(index_elements=["user_id", "material_id"]))
    await session.commit()
    return MessageResponse(detail="Learning progress saved.")


@router.delete("/materials/{material_id}/view", response_model=MessageResponse)
async def reset_material_viewed(
    material_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    material = await session.get(LearningMaterial, material_id)
    if material is None or not material.is_active or not audience_visible(material.audience_code, current_user):
        raise HTTPException(status_code=404, detail="Material not found.")
    await session.execute(delete(LearningProgress).where(
        LearningProgress.user_id == user_id, LearningProgress.material_id == material_id,
    ))
    await session.commit()
    return MessageResponse(detail="Learning progress reset.")
