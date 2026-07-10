from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_code: Mapped[str] = mapped_column(String(50), nullable=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    vk_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    web_push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalendarSubscription(Base):
    __tablename__ = "calendar_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AchievementProgress(Base):
    __tablename__ = "achievement_progress"
    __table_args__ = (UniqueConstraint("user_id", "achievement_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_code: Mapped[str] = mapped_column(String(50), nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
