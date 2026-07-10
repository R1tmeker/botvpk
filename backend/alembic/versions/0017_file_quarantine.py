"""Track malware scan state for uploaded files.

Revision ID: 0016_file_quarantine
Revises: 0015_import_undo
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0016_file_quarantine"
down_revision: str | None = "0015_import_undo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS scan_status VARCHAR(30) NOT NULL DEFAULT 'PENDING'")
    op.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS scan_detail VARCHAR(500)")
    op.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS scanned_at TIMESTAMPTZ")
    op.execute("UPDATE files SET scan_status = 'LEGACY_TRUSTED' WHERE scan_status = 'PENDING'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_status ON files (scan_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_scan_status")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS scanned_at")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS scan_detail")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS scan_status")
