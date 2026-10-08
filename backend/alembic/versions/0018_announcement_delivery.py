"""Make announcement requests repeatable and separate delivery channels."""

from alembic import op
import sqlalchemy as sa

revision = "0017_announcement_delivery"
down_revision = "0016_file_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("announcements", sa.Column("client_request_id", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_announcement_request", "announcements", ["created_by_id", "client_request_id"])
    op.add_column("notifications", sa.Column("send_to_app", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("notifications", "send_to_app")
    op.drop_constraint("uq_announcement_request", "announcements", type_="unique")
    op.drop_column("announcements", "client_request_id")
