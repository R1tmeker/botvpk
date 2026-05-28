from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    user_id: int | None,
    action_code: str,
    entity_name: str | None = None,
    entity_id: int | None = None,
    old_value: dict[str, Any] | list[Any] | None = None,
    new_value: dict[str, Any] | list[Any] | None = None,
    comment: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    item = AuditLog(
        user_id=user_id,
        action_code=action_code,
        entity_name=entity_name,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        comment=comment,
        ip_address=ip_address,
    )
    session.add(item)
    return item


def model_snapshot(obj, fields: list[str]) -> dict[str, Any]:
    return {field: getattr(obj, field) for field in fields}
