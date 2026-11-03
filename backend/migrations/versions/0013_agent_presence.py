"""Presence of agents (who is connected) and their sessions, for the automatic distribution of
new contacts. Only adds tables; no data is changed."""
import sqlalchemy as sa
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    ts = sa.DateTime(timezone=True)
    op.create_table(
        'agent_presence',
        sa.Column('user_id', sa.String(255), primary_key=True),
        sa.Column('role', sa.String(24), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='available'),
        sa.Column('last_heartbeat_at', ts),
        sa.Column('last_visible_at', ts),
        sa.Column('last_assigned_at', ts),
        sa.CheckConstraint("status IN ('available','paused')", name='ck_agent_presence_status'),
    )
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('started_at', ts, nullable=False),
        sa.Column('last_heartbeat_at', ts, nullable=False),
        sa.Column('ended_at', ts),
        sa.Column('connected_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_seconds', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_agent_sessions_user_started', 'agent_sessions', ['user_id', 'started_at'])


def downgrade():
    op.drop_index('ix_agent_sessions_user_started', table_name='agent_sessions')
    op.drop_table('agent_sessions')
    op.drop_table('agent_presence')
