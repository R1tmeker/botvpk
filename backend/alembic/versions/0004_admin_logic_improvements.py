"""Admin roster sync and normative instruction videos.

Revision ID: 0003_admin_logic_improvements
Revises: 0002_alternating_schedule
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0003_admin_logic_improvements"
down_revision: str | None = "0002_alternating_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE normatives ADD COLUMN IF NOT EXISTS instruction_video_file_id INTEGER")
    op.execute("ALTER TABLE normatives ADD COLUMN IF NOT EXISTS instruction_video_url VARCHAR(1000)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_normatives_instruction_video_file_id_files'
            ) THEN
                ALTER TABLE normatives
                ADD CONSTRAINT fk_normatives_instruction_video_file_id_files
                FOREIGN KEY (instruction_video_file_id)
                REFERENCES files(id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE normatives DROP CONSTRAINT IF EXISTS fk_normatives_instruction_video_file_id_files")
    op.execute("ALTER TABLE normatives DROP COLUMN IF EXISTS instruction_video_url")
    op.execute("ALTER TABLE normatives DROP COLUMN IF EXISTS instruction_video_file_id")
