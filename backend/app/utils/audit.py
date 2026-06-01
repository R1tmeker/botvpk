from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

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
    return {field: audit_json_value(getattr(obj, field)) for field in fields}


def audit_json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: audit_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [audit_json_value(item) for item in value]
    return value
