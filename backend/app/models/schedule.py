from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ScheduleTemplate(Base):
    __tablename__ = "schedule_templates"
    __table_args__ = (
        CheckConstraint("week_parity IS NULL OR week_parity IN ('A', 'B')", name="ck_schedule_templates_week_parity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    week_days: Mapped[str] = mapped_column(String(20), nullable=False)
    week_parity: Mapped[str | None] = mapped_column(String(1))
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time)
    place: Mapped[str | None] = mapped_column(String(255))
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id", ondelete="SET NULL"))
    requires_response: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    response_deadline_minutes: Mapped[int | None] = mapped_column(Integer)
    reminder_minutes: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"
    __table_args__ = (
        Index("idx_schedule_events_start", "start_datetime"),
        Index("idx_schedule_events_squad", "squad_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_templates.id", ondelete="SET NULL"))
    event_type_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="CLASS")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    place: Mapped[str | None] = mapped_column(String(255))
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id", ondelete="SET NULL"))
    status_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="PLANNED")
    requires_response: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    response_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grading_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="FIVE_POINT")
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventRecipient(Base):
    __tablename__ = "event_recipients"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("schedule_events.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class EventResponse(Base):
    __tablename__ = "event_responses"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("schedule_events.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    response_code: Mapped[str] = mapped_column(String(50), nullable=False)
    absence_reason_id: Mapped[int | None] = mapped_column(ForeignKey("absence_reasons.id", ondelete="SET NULL"))
    custom_reason: Mapped[str | None] = mapped_column(String(500))
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="MINI_APP")


class AbsenceReason(Base):
    __tablename__ = "absence_reasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    requires_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
