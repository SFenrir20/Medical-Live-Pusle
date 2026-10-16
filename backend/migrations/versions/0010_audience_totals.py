"""Time-weighted audience average and TikTok's own running totals (likes, visitors).

Only adds columns. Existing lives keep their figures; the new fields fill from the next events.
"""
import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('live_metrics', sa.Column(
        'viewer_weighted_sum', sa.BigInteger(), nullable=False, server_default='0'))
    for name in ('viewer_observed_seconds', 'likes_reported_total', 'visitors_reported_total'):
        op.add_column('live_metrics', sa.Column(
            name, sa.Integer(), nullable=False, server_default='0'))
    op.add_column('live_metrics', sa.Column('viewer_last_value', sa.Integer(), nullable=True))
    op.add_column('live_metrics', sa.Column(
        'viewer_last_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in ('viewer_last_at', 'viewer_last_value', 'visitors_reported_total',
                 'likes_reported_total', 'viewer_observed_seconds', 'viewer_weighted_sum'):
        op.drop_column('live_metrics', name)
