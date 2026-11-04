"""WhatsApp images and explicit agent work-session reconnection."""
import sqlalchemy as sa
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('media_id', sa.String(64)))
    op.add_column('agent_presence', sa.Column('idle_since', sa.DateTime(timezone=True)))
    op.add_column('agent_presence', sa.Column('reconnect_required', sa.Boolean(),
                                            nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('agent_presence', 'reconnect_required')
    op.drop_column('agent_presence', 'idle_since')
    op.drop_column('chat_messages', 'media_id')
