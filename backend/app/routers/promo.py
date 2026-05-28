from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import PromoBlock
from ..schemas.core import PromoBlockRead

router = APIRouter(prefix="/promo", tags=["promo"])


def audience_visible(audience_code: str, current_user: CurrentUser) -> bool:
    return audience_code in {"ALL", current_user.role_code}


@router.get("/active", response_model=list[PromoBlockRead])
async def active_promo(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PromoBlock]:
    now = datetime.now(timezone.utc)
    statement = (
        select(PromoBlock)
        .where(PromoBlock.is_active.is_(True))
        .where((PromoBlock.active_from.is_(None)) | (PromoBlock.active_from <= now))
        .where((PromoBlock.active_to.is_(None)) | (PromoBlock.active_to >= now))
        .order_by(PromoBlock.sort_order, PromoBlock.created_at.desc())
    )
    items = list((await session.scalars(statement)).all())
    return [item for item in items if audience_visible(item.audience_code, current_user)]
