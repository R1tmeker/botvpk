from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import CurrentUser, require_role
from ...models import LearningCourse, LearningMaterial
from ...roles import RoleLevel
from ...schemas.core import (
    LearningCourseCreate,
    LearningCourseRead,
    LearningCourseUpdate,
    LearningMaterialCreate,
    LearningMaterialRead,
    LearningMaterialUpdate,
)
from ...utils.audit import model_snapshot, record_audit

router = APIRouter(prefix="/admin/learning", tags=["admin:learning"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/materials", response_model=LearningMaterialRead, status_code=status.HTTP_201_CREATED)
async def create_learning_material(
    payload: LearningMaterialCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> LearningMaterial:
    material = LearningMaterial(**payload.model_dump())
    session.add(material)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="learning_material.create",
        entity_name="learning_materials",
        entity_id=material.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(material)
    return material


@router.patch("/materials/{material_id}", response_model=LearningMaterialRead)
async def update_learning_material(
    material_id: int,
    payload: LearningMaterialUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> LearningMaterial:
    material = await session.get(LearningMaterial, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(material, list(updates))
    for key, value in updates.items():
        setattr(material, key, value)
    material.updated_at = utcnow()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="learning_material.update",
        entity_name="learning_materials",
        entity_id=material.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(material)
    return material


@router.post("/courses", response_model=LearningCourseRead, status_code=status.HTTP_201_CREATED)
async def create_learning_course(
    payload: LearningCourseCreate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> LearningCourse:
    course = LearningCourse(**payload.model_dump())
    session.add(course)
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="learning_course.create",
        entity_name="learning_courses",
        entity_id=course.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(course)
    return course


@router.patch("/courses/{course_id}", response_model=LearningCourseRead)
async def update_learning_course(
    course_id: int,
    payload: LearningCourseUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> LearningCourse:
    course = await session.get(LearningCourse, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    updates = payload.model_dump(exclude_unset=True)
    old = model_snapshot(course, list(updates))
    for key, value in updates.items():
        setattr(course, key, value)
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="learning_course.update",
        entity_name="learning_courses",
        entity_id=course.id,
        old_value=old,
        new_value=updates,
    )
    await session.commit()
    await session.refresh(course)
    return course
