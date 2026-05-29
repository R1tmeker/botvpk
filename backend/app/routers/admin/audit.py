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
    offset: int = 0,
    user_id: int | None = None,
    action_code: str | None = None,
    entity_name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    _=Depends(require_role(RoleLevel.ADMIN)),
) -> list[dict]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id is not None:
        statement = statement.where(AuditLog.user_id == user_id)
    if action_code:
        statement = statement.where(AuditLog.action_code.ilike(f"%{action_code}%"))
    if entity_name:
        statement = statement.where(AuditLog.entity_name == entity_name)
    statement = statement.offset(offset).limit(min(limit, 500))
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
