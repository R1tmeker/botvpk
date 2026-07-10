"""Allow multiple files per normative submission.

Revision ID: 0004_normative_submission_files
Revises: 0003_admin_logic_improvements
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_normative_submission_files"
down_revision: str | None = "0003_admin_logic_improvements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("normative_submission_files"):
        op.create_table(
            "normative_submission_files",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("submission_id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["submission_id"], ["normative_submissions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("submission_id", "file_id"),
        )
        op.create_index(
            "idx_normative_submission_files_submission",
            "normative_submission_files",
            ["submission_id"],
        )
    op.execute(
        """
        INSERT INTO normative_submission_files (submission_id, file_id)
        SELECT id, file_id
        FROM normative_submissions
        WHERE file_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_normative_submission_files_submission", table_name="normative_submission_files")
    op.drop_table("normative_submission_files")
