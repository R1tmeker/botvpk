"""Keep weekly normative submissions as separate historical records."""

from alembic import op
import sqlalchemy as sa

revision = "0019_normative_cycles"
down_revision = "0018_vk_delivery_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE normatives ADD COLUMN IF NOT EXISTS recurrence_days INTEGER")
    op.execute("ALTER TABLE normatives ADD COLUMN IF NOT EXISTS recurrence_start_date DATE")
    op.execute("ALTER TABLE normative_submissions ADD COLUMN IF NOT EXISTS period_start_date DATE")
    op.execute("ALTER TABLE normative_submissions ADD COLUMN IF NOT EXISTS period_end_date DATE")
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("normative_submissions")}
    if "uq_normative_submission_period" not in names:
        op.create_unique_constraint(
            "uq_normative_submission_period", "normative_submissions", ["normative_id", "user_id", "period_start_date"]
        )


def downgrade() -> None:
    op.execute("ALTER TABLE normative_submissions DROP CONSTRAINT IF EXISTS uq_normative_submission_period")
    op.execute("ALTER TABLE normative_submissions DROP COLUMN IF EXISTS period_end_date")
    op.execute("ALTER TABLE normative_submissions DROP COLUMN IF EXISTS period_start_date")
    op.execute("ALTER TABLE normatives DROP COLUMN IF EXISTS recurrence_start_date")
    op.execute("ALTER TABLE normatives DROP COLUMN IF EXISTS recurrence_days")
