from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db_session
from ...config import Settings, get_settings
from ...dependencies.auth import CurrentUser, require_role
from ...models import AuditLog, NotificationPreference, User
from ...roles import RoleLevel
from ...schemas.product import AuditUndoResult
from ...services.sessions import delete_user_sessions
from ...utils.audit import record_audit, utcnow

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
            "undone_at": row.undone_at.isoformat() if row.undone_at else None,
            "undone_by_id": row.undone_by_id,
            "undo_audit_id": row.undo_audit_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/{audit_id}/undo", response_model=AuditUndoResult)
async def undo_audit_operation(
    audit_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuditUndoResult:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    original = await session.scalar(select(AuditLog).where(AuditLog.id == audit_id).with_for_update())
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit operation not found.")
    if original.undone_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audit operation was already undone.")
    if original.action_code not in {"admin.import.commit", "admin.users.bulk"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This operation cannot be undone. File deletion and external messages are never reversible.",
        )
    before_rows = {item["id"]: item for item in (original.old_value or [])}
    after_rows = {item["id"]: item for item in (original.new_value or [])}
    if set(before_rows) != set(after_rows):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audit batch is incomplete.")

    affected_user_ids: list[int] = []
    undo_before: list[dict] = []
    undo_after: list[dict] = []
    for user_id, after_entry in after_rows.items():
        user = await session.scalar(select(User).where(User.id == int(user_id)).with_for_update())
        if user is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User {user_id} no longer exists.")
        if user.role_code == "SUPER_ADMIN" and current_user.role_level < RoleLevel.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only SUPER_ADMIN can undo this batch.")
        current = {field: getattr(user, field) for field in after_entry["after"]}
        expected = after_entry["after"]
        if any(current[field] != expected[field] for field in expected):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User {user_id} changed after the import; undo would overwrite newer data.",
            )
        before_entry = before_rows[user_id]
        before = before_entry.get("before")
        undo_before.append({"id": user.id, "before": current})
        if before is None:
            user.status_code = "ARCHIVED"
            restored = {**current, "status_code": "ARCHIVED"}
        else:
            for field, value in before.items():
                setattr(user, field, value)
            restored = before
        user.token_version += 1
        user.updated_at = utcnow()

        expected_preferences = {
            item["category_code"]: item.get("values") for item in after_entry.get("preferences", [])
        }
        previous_preferences = {
            item["category_code"]: item.get("values") for item in before_entry.get("preferences", [])
        }
        for category, expected_values in expected_preferences.items():
            preference = await session.scalar(
                select(NotificationPreference)
                .where(
                    NotificationPreference.user_id == user.id,
                    NotificationPreference.category_code == category,
                )
                .with_for_update()
            )
            if preference is None or any(
                getattr(preference, field) != value for field, value in (expected_values or {}).items()
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Notification preferences for user {user_id} changed after the operation.",
                )
            previous_values = previous_preferences.get(category)
            if previous_values is None:
                await session.delete(preference)
            else:
                for field, value in previous_values.items():
                    setattr(preference, field, value)
                preference.updated_at = utcnow()
        affected_user_ids.append(user.id)
        undo_after.append({"id": user.id, "after": restored, "preferences": before_entry.get("preferences", [])})

    undo_audit = await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="admin.audit.undo",
        entity_name=original.entity_name,
        entity_id=original.id,
        old_value=undo_before,
        new_value=undo_after,
        comment=f"Undo audit batch {original.id}",
    )
    await session.flush()
    original.undone_at = utcnow()
    original.undone_by_id = current_user.user_id
    original.undo_audit_id = undo_audit.id
    await session.commit()
    for user_id in affected_user_ids:
        await delete_user_sessions(settings, user_id)
    return AuditUndoResult(
        audit_id=original.id,
        undo_audit_id=undo_audit.id,
        affected=len(affected_user_ids),
        detail="Audit operation undone.",
    )
