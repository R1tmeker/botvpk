from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PromoBlock(Base):
    __tablename__ = "promo_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    image_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    button_text: Mapped[str | None] = mapped_column(String(100))
    button_url: Mapped[str | None] = mapped_column(String(1000))
    action_type_code: Mapped[str | None] = mapped_column(String(50))
    audience_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ALL")
    style_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="DEFAULT")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MenuCard(Base):
    __tablename__ = "menu_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    icon_code: Mapped[str | None] = mapped_column(String(100))
    color_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="DEFAULT")
    route: Mapped[str | None] = mapped_column(String(255))
    roles_json: Mapped[dict | list | None] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    show_badge: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserDashboardSetting(Base):
    __tablename__ = "user_dashboard_settings"
    __table_args__ = (UniqueConstraint("user_id", "block_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    block_code: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    view_mode_code: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
