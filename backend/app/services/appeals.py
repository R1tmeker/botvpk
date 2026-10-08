from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Appeal, AppealMessage, Notification, User
from ..roles import ADMIN_ROLES, PLATOON_ROLES, RoleLevel
from ..utils.audit import record_audit, utcnow
from .appeal_policy import can_access_appeal, reply_recipient_ids, validate_appeal_text
from .realtime import publish_realtime_event


async def notify_appeal_commanders(session: AsyncSession, appeal: Appeal, *, sender_id: int, title: str, body: str) -> None:
    ids = list((await session.scalars(select(User.id).where(
        User.status_code == "ACTIVE", User.role_code.in_(PLATOON_ROLES | ADMIN_ROLES),
    ))).all())
    for recipient_id in reply_recipient_ids(
        author_id=appeal.author_user_id, sender_id=sender_id, commander_ids=ids, assignee_id=appeal.assignee_user_id,
    ):
        session.add(Notification(
            user_id=recipient_id, type_code="APPEAL", category_code="APPEALS", title=title, body=body,
            entity_name="appeals", entity_id=appeal.id, deep_link=f"/appeals?id={appeal.id}", send_to_tg=True,
        ))


async def add_appeal_reply(session: AsyncSession, appeal: Appeal, *, sender_id: int, role: RoleLevel, body: str) -> AppealMessage:
    if not can_access_appeal(author_id=appeal.author_user_id, user_id=sender_id, role=role):
        raise PermissionError("Нет доступа к этому обращению.")
    message = AppealMessage(appeal_id=appeal.id, author_id=sender_id, body=validate_appeal_text(body))
    session.add(message)
    appeal.updated_at = utcnow()
    if sender_id == appeal.author_user_id and appeal.status_code == "NEEDS_INFO":
        appeal.status_code = "IN_PROGRESS"
    await session.flush()
    await record_audit(session, user_id=sender_id, action_code="appeal.message", entity_name="appeals",
                       entity_id=appeal.id, new_value={"message_id": message.id})
    await notify_appeal_commanders(session, appeal, sender_id=sender_id, title="Новое сообщение в обращении",
                                  body=f"Новое сообщение в обращении «{appeal.subject}»")
    return message


async def publish_appeal_update() -> None:
    # Invalidate caches without broadcasting the private conversation or its IDs.
    await publish_realtime_event(get_settings(), event_type="appeals.updated", query_keys=["appeals", "admin", "notifications", "dashboard"])
