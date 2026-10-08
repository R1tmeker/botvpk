"""Make announcement requests repeatable and separate delivery channels."""

from alembic import op
import sqlalchemy as sa

revision = "0017_announcement_delivery"
down_revision = "0016_file_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration uses current Base.metadata, so clean installs may already contain these fields.
    op.execute("ALTER TABLE announcements ADD COLUMN IF NOT EXISTS client_request_id VARCHAR(36)")
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("announcements")}
    if "uq_announcement_request" not in names:
        op.create_unique_constraint("uq_announcement_request", "announcements", ["created_by_id", "client_request_id"])
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS send_to_app BOOLEAN NOT NULL DEFAULT TRUE")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS send_to_app")
    op.execute("ALTER TABLE announcements DROP CONSTRAINT IF EXISTS uq_announcement_request")
    op.execute("ALTER TABLE announcements DROP COLUMN IF EXISTS client_request_id")
