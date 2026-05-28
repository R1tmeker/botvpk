"""Add user avatar file reference.

Revision ID: 0002_user_avatar
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_user_avatar"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_file_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_avatar_file_id_files",
        "users",
        "files",
        ["avatar_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_avatar_file_id_files", "users", type_="foreignkey")
    op.drop_column("users", "avatar_file_id")
