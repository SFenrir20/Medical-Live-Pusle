"""Branches (sedes), advisor shifts, the branch of a conversation with its appointment, branch
funnels and the log of automatic rules. Additive only."""
import sqlalchemy as sa
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)
BIG = sa.BigInteger()


def upgrade():
    op.create_table(
        'crm_sites',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(30), nullable=False, unique=True),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )
    op.create_table(
        'crm_staff',
        sa.Column('user_id', sa.String(255), primary_key=True),
        sa.Column('site_id', BIG, sa.ForeignKey('crm_sites.id'), nullable=False),
        sa.Column('shift_start', sa.String(5), nullable=False, server_default='09:00'),
        sa.Column('shift_end', sa.String(5), nullable=False, server_default='18:00'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.create_index('ix_crm_staff_site', 'crm_staff', ['site_id'])
    op.create_table(
        'crm_auto_log',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('message_id', BIG),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('summary', sa.String(300), nullable=False),
        sa.Column('before', sa.JSON()),
        sa.Column('undone_at', ts),
        sa.Column('undone_by', sa.String(255)),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ux_crm_auto_message', 'crm_auto_log', ['kind', 'message_id'], unique=True)
    op.create_index('ix_crm_auto_conv', 'crm_auto_log', ['conversation_id', 'created_at'])
    op.add_column('chat_conversations', sa.Column('site_id', BIG))
    op.add_column('chat_conversations', sa.Column('appointment_at', ts))
    op.add_column('chat_conversations', sa.Column('appointment_label', sa.String(80)))
    op.create_index('ix_chat_conversations_site', 'chat_conversations', ['site_id'])
    op.add_column('crm_pipelines', sa.Column('site_id', BIG))


def downgrade():
    op.drop_column('crm_pipelines', 'site_id')
    op.drop_index('ix_chat_conversations_site', 'chat_conversations')
    for name in ('appointment_label', 'appointment_at', 'site_id'):
        op.drop_column('chat_conversations', name)
    op.drop_table('crm_auto_log')
    op.drop_table('crm_staff')
    op.drop_table('crm_sites')
