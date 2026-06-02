"""Add user profile location fields.

Revision ID: 0005_user_profile_location
Revises: 0004_normative_submission_files
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0005_user_profile_location"
down_revision: str | None = "0004_normative_submission_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS education_place VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS education_place")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS city")
