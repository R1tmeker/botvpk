"""Auth hardening fields and hot-path indexes.

Revision ID: 0008_auth_security_and_indexes
Revises: 0007_vk_linking
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0008_auth_security_and_indexes"
down_revision: str | None = "0007_vk_linking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0")

    op.execute("CREATE INDEX IF NOT EXISTS idx_event_responses_event_user ON event_responses (event_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_event_responses_user_event ON event_responses (user_id, event_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_event_user ON attendance (event_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications (user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notifications_created")
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_created")
    op.execute("DROP INDEX IF EXISTS idx_attendance_event_user")
    op.execute("DROP INDEX IF EXISTS idx_event_responses_user_event")
    op.execute("DROP INDEX IF EXISTS idx_event_responses_event_user")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locked_until")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS failed_login_count")
