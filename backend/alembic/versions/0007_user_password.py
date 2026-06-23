"""Add password credentials for website login.

Revision ID: 0006_user_password
Revises: 0005_user_profile_location
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0006_user_password"
down_revision: str | None = "0005_user_profile_location"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_set_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_set_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
