from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    importance_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="NORMAL")
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ALL")
    target_squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id", ondelete="SET NULL"))
    target_role_code: Mapped[str | None] = mapped_column(String(50))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    send_to_tg: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    send_to_app: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    require_read_confirm: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="DRAFT")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
