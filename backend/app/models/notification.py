from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("idx_notifications_user", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    entity_name: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    category_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="SYSTEM")
    priority_code: Mapped[str] = mapped_column(String(20), nullable=False, server_default="NORMAL")
    deep_link: Mapped[str | None] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    send_to_tg: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    tg_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vk_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    web_push_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_error: Mapped[str | None] = mapped_column(Text)
    deliver_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


@event.listens_for(Notification, "before_insert")
def assign_notification_category(_mapper, _connection, target: Notification) -> None:
    if not target.category_code:
        type_code = target.type_code.upper()
        if type_code.startswith("SCHEDULE") or type_code.startswith("EVENT"):
            target.category_code = "SCHEDULE"
        elif type_code.startswith("ATTENDANCE"):
            target.category_code = "ATTENDANCE"
        elif type_code.startswith("NORMATIVE"):
            target.category_code = "NORMATIVES"
        elif type_code.startswith("ANNOUNCEMENT"):
            target.category_code = "ANNOUNCEMENTS"
        elif type_code.startswith("APPEAL"):
            target.category_code = "APPEALS"
        else:
            target.category_code = "SYSTEM"
    if target.deep_link or target.entity_id is None:
        return
    if target.entity_name == "schedule_events":
        target.deep_link = f"/schedule?event={target.entity_id}"
    elif target.entity_name in {"normatives", "normative_submissions"}:
        target.deep_link = f"/normatives?id={target.entity_id}"
    elif target.entity_name == "appeals":
        target.deep_link = f"/appeals?id={target.entity_id}"
    elif target.entity_name == "attendance":
        target.deep_link = f"/attendance?id={target.entity_id}"
    elif target.entity_name == "join_applications":
        target.deep_link = f"/admin/applications?id={target.entity_id}"
