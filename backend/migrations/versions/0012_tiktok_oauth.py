"""Persist one-use OAuth attempts and encrypted TikTok advertiser credentials."""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tiktok_oauth_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("app_id", sa.String(100), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tiktok_oauth_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("app_id", sa.String(100), nullable=False),
        sa.Column("authorized_by", sa.String(128), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("advertiser_ids", sa.JSON(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("tiktok_oauth_connections")
    op.drop_table("tiktok_oauth_attempts")
