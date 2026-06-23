"""Alternating schedule templates and overridden events.

Revision ID: 0002_alternating_schedule
Revises: 0002_user_avatar
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0002_alternating_schedule"
down_revision: str | None = "0002_user_avatar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE schedule_templates ADD COLUMN IF NOT EXISTS week_parity VARCHAR(1)")
    op.execute("ALTER TABLE schedule_events ADD COLUMN IF NOT EXISTS is_overridden BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_schedule_templates_week_parity'
            ) THEN
                ALTER TABLE schedule_templates
                ADD CONSTRAINT ck_schedule_templates_week_parity
                CHECK (week_parity IS NULL OR week_parity IN ('A', 'B'));
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ('schedule_week_a_start', '2026-06-02')
        ON CONFLICT (key) DO UPDATE
        SET value = COALESCE(settings.value, EXCLUDED.value)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schedule_templates DROP CONSTRAINT IF EXISTS ck_schedule_templates_week_parity")
    op.execute("ALTER TABLE schedule_events DROP COLUMN IF EXISTS is_overridden")
    op.execute("ALTER TABLE schedule_templates DROP COLUMN IF EXISTS week_parity")
    op.execute("DELETE FROM settings WHERE key = 'schedule_week_a_start' AND value = '2026-06-02'")
