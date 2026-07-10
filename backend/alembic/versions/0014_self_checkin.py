"""Add server-controlled self check-in and attendance source audit.

Revision ID: 0013_self_checkin
Revises: 0012_security_sessions
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0013_self_checkin"
down_revision: str | None = "0012_security_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE schedule_events "
        "ADD COLUMN IF NOT EXISTS self_checkin_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE schedule_events ADD COLUMN IF NOT EXISTS self_checkin_opens_at TIMESTAMPTZ")
    op.execute("ALTER TABLE schedule_events ADD COLUMN IF NOT EXISTS self_checkin_closes_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE schedule_events "
        "ADD COLUMN IF NOT EXISTS late_after_minutes INTEGER NOT NULL DEFAULT 5"
    )
    op.execute(
        "ALTER TABLE attendance "
        "ADD COLUMN IF NOT EXISTS source_code VARCHAR(50) NOT NULL DEFAULT 'COMMANDER'"
    )
    op.execute("ALTER TABLE attendance_history ADD COLUMN IF NOT EXISTS old_source_code VARCHAR(50)")
    op.execute("ALTER TABLE attendance_history ADD COLUMN IF NOT EXISTS new_source_code VARCHAR(50)")
    op.execute(
        "ALTER TABLE schedule_events DROP CONSTRAINT IF EXISTS ck_schedule_events_late_after_minutes"
    )
    op.execute(
        "ALTER TABLE schedule_events ADD CONSTRAINT ck_schedule_events_late_after_minutes "
        "CHECK (late_after_minutes BETWEEN 0 AND 1440)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_events_self_checkin "
        "ON schedule_events (self_checkin_enabled, start_datetime)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_events_self_checkin")
    op.execute("ALTER TABLE schedule_events DROP CONSTRAINT IF EXISTS ck_schedule_events_late_after_minutes")
    op.execute("ALTER TABLE attendance_history DROP COLUMN IF EXISTS new_source_code")
    op.execute("ALTER TABLE attendance_history DROP COLUMN IF EXISTS old_source_code")
    op.execute("ALTER TABLE attendance DROP COLUMN IF EXISTS source_code")
    op.execute("ALTER TABLE schedule_events DROP COLUMN IF EXISTS late_after_minutes")
    op.execute("ALTER TABLE schedule_events DROP COLUMN IF EXISTS self_checkin_closes_at")
    op.execute("ALTER TABLE schedule_events DROP COLUMN IF EXISTS self_checkin_opens_at")
    op.execute("ALTER TABLE schedule_events DROP COLUMN IF EXISTS self_checkin_enabled")
