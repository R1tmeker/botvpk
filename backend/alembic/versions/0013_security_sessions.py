"""Protect TOTP and one-time link codes.

Revision ID: 0012_security_sessions
Revises: 0011_perf_pagination_indexes
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0012_security_sessions"
down_revision: str | None = "0011_perf_pagination_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret_encrypted TEXT")
    op.execute("ALTER TABLE channel_link_codes ALTER COLUMN code DROP NOT NULL")
    op.execute("ALTER TABLE channel_link_codes ADD COLUMN IF NOT EXISTS code_digest VARCHAR(64)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_link_codes_digest "
        "ON channel_link_codes (channel, code_digest)"
    )
    op.execute(
        "UPDATE channel_link_codes SET used_at = NOW() "
        "WHERE used_at IS NULL AND code_digest IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_link_codes_digest")
    op.execute("ALTER TABLE channel_link_codes DROP COLUMN IF EXISTS code_digest")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_secret_encrypted")
