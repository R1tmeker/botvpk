from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Appeal, LearningMaterial, Normative, ScheduleEvent, User
from ..roles import RoleLevel
from ..schemas.product import SearchResult

router = APIRouter(prefix="/search", tags=["search"])


def search_pattern(query: str) -> str:
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", response_model=list[SearchResult])
async def global_search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=30, ge=1, le=50),
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[SearchResult]:
    pattern = search_pattern(q)
    per_type = min(15, limit)
    results: list[SearchResult] = []

    event_query = select(ScheduleEvent).where(
        or_(ScheduleEvent.title.ilike(pattern, escape="\\"), ScheduleEvent.description.ilike(pattern, escape="\\")),
        or_(ScheduleEvent.squad_id.is_(None), ScheduleEvent.squad_id == current_user.squad_id),
    )
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        event_query = select(ScheduleEvent).where(
            or_(ScheduleEvent.title.ilike(pattern, escape="\\"), ScheduleEvent.description.ilike(pattern, escape="\\"))
        )
    for item in (await session.scalars(event_query.order_by(ScheduleEvent.start_datetime.desc()).limit(per_type))).all():
        results.append(
            SearchResult(
                type="event",
                id=item.id,
                title=item.title,
                description=item.place,
                deep_link=f"/schedule?event={item.id}",
            )
        )

    normative_query = select(Normative).where(
        Normative.is_active.is_(True),
        or_(Normative.title.ilike(pattern, escape="\\"), Normative.description.ilike(pattern, escape="\\")),
        or_(Normative.squad_id.is_(None), Normative.squad_id == current_user.squad_id),
    )
    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        normative_query = select(Normative).where(
            Normative.is_active.is_(True),
            or_(Normative.title.ilike(pattern, escape="\\"), Normative.description.ilike(pattern, escape="\\")),
        )
    for item in (await session.scalars(normative_query.order_by(Normative.created_at.desc()).limit(per_type))).all():
        results.append(
            SearchResult(
                type="normative",
                id=item.id,
                title=item.title,
                description=item.description,
                deep_link=f"/normatives?id={item.id}",
            )
        )

    materials = (
        await session.scalars(
            select(LearningMaterial)
            .where(
                LearningMaterial.is_active.is_(True),
                or_(
                    LearningMaterial.title.ilike(pattern, escape="\\"),
                    LearningMaterial.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(LearningMaterial.published_at.desc().nullslast())
            .limit(per_type)
        )
    ).all()
    results.extend(
        SearchResult(
            type="material",
            id=item.id,
            title=item.title,
            description=item.description,
            deep_link=f"/learning?material={item.id}",
        )
        for item in materials
    )

    if current_user.user_id is not None:
        appeals_query = select(Appeal).where(
            or_(Appeal.subject.ilike(pattern, escape="\\"), Appeal.description.ilike(pattern, escape="\\"))
        )
        if current_user.role_level < RoleLevel.SQUAD_COMMANDER:
            appeals_query = appeals_query.where(Appeal.author_user_id == current_user.user_id)
        for item in (await session.scalars(appeals_query.order_by(Appeal.created_at.desc()).limit(per_type))).all():
            results.append(
                SearchResult(
                    type="appeal",
                    id=item.id,
                    title=item.subject,
                    description=item.status_code,
                    deep_link=f"/appeals?id={item.id}",
                )
            )

    if current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        users_query = select(User).where(
            User.status_code == "ACTIVE",
            or_(User.full_name.ilike(pattern, escape="\\"), User.username.ilike(pattern, escape="\\")),
        )
        if current_user.role_level < RoleLevel.SQUAD_COMMANDER:
            users_query = users_query.where(User.squad_id == current_user.squad_id)
        for item in (await session.scalars(users_query.order_by(User.full_name).limit(per_type))).all():
            results.append(
                SearchResult(
                    type="person",
                    id=item.id,
                    title=item.full_name,
                    description=f"@{item.username}" if item.username else None,
                    deep_link=f"/attendance?user={item.id}",
                )
            )

    type_order = {"event": 0, "normative": 1, "material": 2, "appeal": 3, "person": 4}
    return sorted(results, key=lambda item: (type_order[item.type], item.title.casefold()))[:limit]
