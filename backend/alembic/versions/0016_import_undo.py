"""Track reversible audit operations.

Revision ID: 0015_import_undo
Revises: 0014_product_features
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0015_import_undo"
down_revision: str | None = "0014_product_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS undone_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS undone_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS undo_audit_id BIGINT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_undone ON audit_log (undone_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_log_undone")
    op.execute("ALTER TABLE audit_log DROP COLUMN IF EXISTS undo_audit_id")
    op.execute("ALTER TABLE audit_log DROP COLUMN IF EXISTS undone_by_id")
    op.execute("ALTER TABLE audit_log DROP COLUMN IF EXISTS undone_at")
