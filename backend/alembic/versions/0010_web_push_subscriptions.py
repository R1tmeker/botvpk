"""Add Web Push subscriptions.

Revision ID: 0009_web_push_subscriptions
Revises: 0008_auth_security_and_indexes
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0009_web_push_subscriptions"
down_revision: str | None = "0008_auth_security_and_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS web_push_sent_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS web_push_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint VARCHAR(500) NOT NULL,
            subscription_json JSONB NOT NULL,
            user_agent VARCHAR(500),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_push_subscriptions_endpoint ON web_push_subscriptions (endpoint)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_web_push_subscriptions_user ON web_push_subscriptions (user_id, is_active)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_web_push_subscriptions_user")
    op.execute("DROP INDEX IF EXISTS idx_web_push_subscriptions_endpoint")
    op.execute("DROP TABLE IF EXISTS web_push_subscriptions")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS web_push_sent_at")
