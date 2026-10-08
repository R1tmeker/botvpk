from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..roles import RoleLevel
from ..schemas.product import SearchResult
from ..services.search import search_accessible, search_pattern  # noqa: F401

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[SearchResult])
async def global_search(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=30, ge=1, le=50),
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[SearchResult]:
    return await search_accessible(
        session, q, role=current_user.role_level, role_code=current_user.role_code,
        squad_id=current_user.squad_id, user_id=current_user.user_id, limit=limit,
    )
