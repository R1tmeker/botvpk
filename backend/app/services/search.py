from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Appeal, LearningMaterial, Normative, ScheduleEvent, User
from ..roles import RoleLevel
from ..schemas.product import SearchResult
from .audiences import visible_audiences


def search_pattern(query: str) -> str:
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def search_accessible(
    session: AsyncSession, query: str, *, role: RoleLevel, role_code: str,
    squad_id: int | None, user_id: int | None, limit: int = 30,
) -> list[SearchResult]:
    if role < RoleLevel.PARTICIPANT or len(query.strip()) < 2:
        return []
    pattern = search_pattern(query)
    per_type = min(15, limit)
    results: list[SearchResult] = []

    event_query = select(ScheduleEvent).where(
        or_(ScheduleEvent.title.ilike(pattern, escape="\\"), ScheduleEvent.description.ilike(pattern, escape="\\")),
        or_(ScheduleEvent.squad_id.is_(None), ScheduleEvent.squad_id == squad_id),
    )
    if role >= RoleLevel.SQUAD_COMMANDER:
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
        or_(Normative.squad_id.is_(None), Normative.squad_id == squad_id),
    )
    if role >= RoleLevel.SQUAD_COMMANDER:
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
                LearningMaterial.audience_code.in_(visible_audiences(role_code, role)),
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

    if user_id is not None:
        appeals_query = select(Appeal).where(
            or_(Appeal.subject.ilike(pattern, escape="\\"), Appeal.description.ilike(pattern, escape="\\"))
        )
        if role < RoleLevel.DEPUTY_PLATOON_COMMANDER:
            appeals_query = appeals_query.where(Appeal.author_user_id == user_id)
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

    if role >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        users_query = select(User).where(
            User.status_code == "ACTIVE",
            or_(User.full_name.ilike(pattern, escape="\\"), User.username.ilike(pattern, escape="\\")),
        )
        if role < RoleLevel.SQUAD_COMMANDER:
            users_query = users_query.where(User.squad_id == squad_id)
        for item in (await session.scalars(users_query.order_by(User.full_name).limit(per_type))).all():
            results.append(
                SearchResult(
                    type="person",
                    id=item.id,
                    title=item.full_name,
                    description=f"@{item.username}" if item.username else None,
                    deep_link=f"/people?user={item.id}",
                )
            )

    # Interleave categories so many event matches cannot hide people or appeals.
    groups = [[item for item in results if item.type == kind] for kind in ("event", "normative", "material", "appeal", "person")]
    ranked: list[SearchResult] = []
    for position in range(per_type):
        for group in groups:
            if position < len(group):
                ranked.append(group[position])
    return ranked[:limit]
