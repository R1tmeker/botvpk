"""Track deferred and suppressed VK deliveries without losing inbox history."""

from alembic import op

revision = "0018_vk_delivery_guard"
down_revision = "0017_announcement_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clean installs use current Base.metadata in the initial migration.
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS vk_retry_after TIMESTAMPTZ")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS vk_suppressed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS vk_suppression_reason VARCHAR(100)")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS vk_suppression_reason")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS vk_suppressed_at")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS vk_retry_after")
