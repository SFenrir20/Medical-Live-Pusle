"""Persist attendance independently of TikTok broadcasts."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shifts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("end_reason", sa.String(16)),
        sa.Column("closed_by", sa.String(255)),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_shift_time"),
        sa.CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL AND closed_by IS NULL) OR "
            "(ended_at IS NOT NULL AND end_reason IS NOT NULL "
            "AND end_reason IN ('manual', 'handover') AND closed_by IS NOT NULL)",
            name="ck_shift_closure"),
    )
    op.create_index("uq_active_shift_per_account", "shifts", ["account_id"], unique=True,
                    postgresql_where=sa.text("ended_at IS NULL"))
    op.create_index("ix_shifts_user_started", "shifts", ["user_id", "started_at", "id"])


def downgrade():
    op.drop_table("shifts")
