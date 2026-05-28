from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...dependencies.auth import require_role
from ...models import AuditLog
from ...roles import RoleLevel

router = APIRouter(prefix="/admin/audit", tags=["admin:audit"])


@router.get("", response_model=list[dict])
async def audit_log(
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.ADMIN)),
) -> list[dict]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    rows = list((await session.scalars(statement)).all())
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action_code": row.action_code,
            "entity_name": row.entity_name,
            "entity_id": row.entity_id,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "comment": row.comment,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
