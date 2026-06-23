"""Add VK channel: vk_id on users and channel_link_codes table.

Revision ID: 0007_vk_linking
Revises: 0006_user_password
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0007_vk_linking"
down_revision: str | None = "0006_user_password"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS vk_id BIGINT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_vk_id ON users (vk_id) WHERE vk_id IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_link_codes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel VARCHAR(20) NOT NULL DEFAULT 'VK',
            code VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_link_codes_code ON channel_link_codes (channel, code)"
    )
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS vk_sent_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS vk_sent_at")
    op.execute("DROP TABLE IF EXISTS channel_link_codes")
    op.execute("DROP INDEX IF EXISTS uq_users_vk_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS vk_id")
