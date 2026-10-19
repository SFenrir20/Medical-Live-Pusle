"""Ranking of fans: counters per user and live (comments, likes, gifts, follows, presence).

Creates audience_members and fills it from the raw events still stored (last
COMMENTS_RETENTION_DAYS), so the lives that already happened have a ranking. Nothing existing is
changed.
"""
import sqlalchemy as sa
from alembic import context, op

from livepulse.modules.social_live.audience import backfill_from_raw_events

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    ts = sa.DateTime(timezone=True)
    op.create_table(
        'audience_members',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('live_id', sa.String(40), sa.ForeignKey('lives.id'), nullable=False),
        sa.Column('user_key', sa.String(128), nullable=False),
        sa.Column('username', sa.String(128), nullable=False),
        sa.Column('display_name', sa.String(128)),
        sa.Column('first_seen_at', ts, nullable=False),
        sa.Column('last_seen_at', ts, nullable=False),
        sa.Column('comments', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('likes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('shares', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gifts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('diamonds', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('follows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('joins', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('live_id', 'user_key', name='uq_audience_live_user'),
    )
    op.create_index('ix_audience_user', 'audience_members', ['user_key'])
    op.create_index('ix_audience_last_seen', 'audience_members', ['last_seen_at'])
    if not context.is_offline_mode():  # `alembic ... --sql` only renders the schema
        backfill_from_raw_events(op.get_bind())


def downgrade():
    op.drop_index('ix_audience_last_seen', table_name='audience_members')
    op.drop_index('ix_audience_user', table_name='audience_members')
    op.drop_table('audience_members')
