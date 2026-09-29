"""0001: broadcasts + raw_events (+ idempotency_keys existente).

Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("tiktok_username", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "raw_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=32), nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_raw_events_account_occurred", "raw_events",
                    ["account_id", "occurred_at"])
    # Modelo ya existente (shared/idempotency.py), se incluye para que
    # `upgrade head` deje la BD igual a Base.metadata.
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("response", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_index("ix_raw_events_account_occurred", table_name="raw_events")
    op.drop_table("raw_events")
    op.drop_table("broadcasts")
