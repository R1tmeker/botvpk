from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification
from ..utils.audit import utcnow


async def inbox_counts(session: AsyncSession, user_id: int, *, app_only: bool = False) -> dict[str, int]:
    statement = select(func.count(Notification.id), func.count(Notification.id).filter(Notification.is_read.is_(False))).where(Notification.user_id == user_id)
    if app_only:
        statement = statement.where(Notification.send_to_app.is_(True))
    total, unread = (await session.execute(statement)).one()
    return {"total": total, "unread": unread}


async def inbox_page(
    session: AsyncSession, user_id: int, *, unread_only: bool = False,
    category: str | None = None, query: str | None = None, limit: int = 50, offset: int = 0, app_only: bool = False,
) -> list[Notification]:
    statement = select(Notification).where(Notification.user_id == user_id)
    if app_only:
        statement = statement.where(Notification.send_to_app.is_(True))
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))
    if category:
        statement = statement.where(Notification.category_code == category)
    if query and query.strip():
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            Notification.title.ilike(pattern, escape="\\") | Notification.body.ilike(pattern, escape="\\")
        )
    statement = statement.order_by(
        Notification.is_pinned.desc(), Notification.created_at.desc(), Notification.id.desc(),
    ).limit(limit).offset(offset)
    return list((await session.scalars(statement)).all())


async def mark_notification_read(session: AsyncSession, user_id: int, notification_id: int) -> Notification | None:
    item = await session.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id))
    if item is not None and not item.is_read:
        item.is_read = True
        item.read_at = utcnow()
    return item


async def mark_inbox_read(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        update(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=utcnow())
    )
    return result.rowcount
