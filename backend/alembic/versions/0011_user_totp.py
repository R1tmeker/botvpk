"""Add user TOTP fields.

Revision ID: 0010_user_totp
Revises: 0009_web_push_subscriptions
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0010_user_totp"
down_revision: str | None = "0009_web_push_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_enabled_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_secret")
