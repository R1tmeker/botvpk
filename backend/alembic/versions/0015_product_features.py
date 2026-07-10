"""Add preferences, calendar subscriptions, achievements and delivery state.

Revision ID: 0014_product_features
Revises: 0013_self_checkin
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0014_product_features"
down_revision: str | None = "0013_self_checkin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS notification_preferences ("
        "id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "category_code VARCHAR(50) NOT NULL, telegram_enabled BOOLEAN NOT NULL DEFAULT TRUE, "
        "vk_enabled BOOLEAN NOT NULL DEFAULT TRUE, web_push_enabled BOOLEAN NOT NULL DEFAULT FALSE, "
        "in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE, quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE, "
        "quiet_hours_start TIME, quiet_hours_end TIME, updated_at TIMESTAMPTZ, "
        "UNIQUE (user_id, category_code))"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS calendar_subscriptions ("
        "id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, "
        "token_digest VARCHAR(64) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "revoked_at TIMESTAMPTZ)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS achievement_progress ("
        "id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "achievement_code VARCHAR(50) NOT NULL, current_value INTEGER NOT NULL DEFAULT 0, "
        "target_value INTEGER NOT NULL, unlocked_at TIMESTAMPTZ, is_public BOOLEAN NOT NULL DEFAULT FALSE, "
        "updated_at TIMESTAMPTZ, UNIQUE (user_id, achievement_code))"
    )
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS category_code VARCHAR(50) NOT NULL DEFAULT 'SYSTEM'")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS priority_code VARCHAR(20) NOT NULL DEFAULT 'NORMAL'")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS deep_link VARCHAR(500)")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS delivery_error TEXT")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS deliver_after TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notification_preferences_user ON notification_preferences (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_calendar_subscriptions_digest ON calendar_subscriptions (token_digest)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_achievement_progress_user ON achievement_progress (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_delivery ON notifications (deliver_after, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notifications_delivery")
    op.execute("DROP INDEX IF EXISTS idx_achievement_progress_user")
    op.execute("DROP INDEX IF EXISTS idx_calendar_subscriptions_digest")
    op.execute("DROP INDEX IF EXISTS idx_notification_preferences_user")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS deliver_after")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS delivery_error")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS deep_link")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS priority_code")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS category_code")
    op.execute("DROP TABLE IF EXISTS achievement_progress")
    op.execute("DROP TABLE IF EXISTS calendar_subscriptions")
    op.execute("DROP TABLE IF EXISTS notification_preferences")
