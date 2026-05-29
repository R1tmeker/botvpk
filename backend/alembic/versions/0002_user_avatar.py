"""Add user avatar file reference.

Revision ID: 0002_user_avatar
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0002_user_avatar"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_file_id INTEGER")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_users_avatar_file_id_files'
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_avatar_file_id_files
                FOREIGN KEY (avatar_file_id)
                REFERENCES files(id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_avatar_file_id_files", "users", type_="foreignkey")
    op.drop_column("users", "avatar_file_id")
