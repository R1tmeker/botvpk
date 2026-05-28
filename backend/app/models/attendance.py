from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id"),
        Index("idx_attendance_event", "event_id"),
        Index("idx_attendance_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("schedule_events.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="NOT_MARKED")
    absence_reason_id: Mapped[int | None] = mapped_column(ForeignKey("absence_reasons.id", ondelete="SET NULL"))
    custom_reason: Mapped[str | None] = mapped_column(String(500))
    marked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceGrade(Base):
    __tablename__ = "attendance_grades"
    __table_args__ = (UniqueConstraint("attendance_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendance_id: Mapped[int] = mapped_column(ForeignKey("attendance.id", ondelete="CASCADE"), nullable=False)
    grade_value: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    set_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceHistory(Base):
    __tablename__ = "attendance_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendance_id: Mapped[int] = mapped_column(ForeignKey("attendance.id", ondelete="CASCADE"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(50))
    new_status: Mapped[str | None] = mapped_column(String(50))
    old_grade: Mapped[str | None] = mapped_column(String(20))
    new_grade: Mapped[str | None] = mapped_column(String(20))
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
