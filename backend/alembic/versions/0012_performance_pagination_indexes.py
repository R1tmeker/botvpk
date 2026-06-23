"""Add pagination helper indexes.

Revision ID: 0011_performance_pagination_indexes
Revises: 0010_user_totp
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0011_performance_pagination_indexes"
down_revision: str | None = "0010_user_totp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_user_updated ON attendance (user_id, updated_at DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_normative_submissions_user_submitted "
        "ON normative_submissions (user_id, submitted_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_normative_submissions_status_submitted "
        "ON normative_submissions (status_code, submitted_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_normative_submissions_status_submitted")
    op.execute("DROP INDEX IF EXISTS idx_normative_submissions_user_submitted")
    op.execute("DROP INDEX IF EXISTS idx_attendance_user_updated")
