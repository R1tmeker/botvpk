from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Normative(Base):
    __tablename__ = "normatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type_code: Mapped[str] = mapped_column(String(100), nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_audience: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ALL")
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id", ondelete="SET NULL"))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    instruction_video_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    instruction_video_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NormativeTarget(Base):
    __tablename__ = "normative_targets"
    __table_args__ = (UniqueConstraint("normative_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normative_id: Mapped[int] = mapped_column(ForeignKey("normatives.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class NormativeSubmission(Base):
    __tablename__ = "normative_submissions"
    __table_args__ = (
        Index("idx_normative_submissions_user", "user_id"),
        Index("idx_normative_submissions_status", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normative_id: Mapped[int] = mapped_column(ForeignKey("normatives.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status_code: Mapped[str] = mapped_column(String(50), nullable=False, server_default="PENDING")
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(Text)
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    grade_value: Mapped[str | None] = mapped_column(String(20))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
