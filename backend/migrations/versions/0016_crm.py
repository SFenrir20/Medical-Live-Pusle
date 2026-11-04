"""CRM over the chat conversations: stage/result/archive on the conversation, internal notes,
scheduled messages, WhatsApp consent and pre-written messages. Additive only."""
import sqlalchemy as sa
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)
BIG = sa.BigInteger()


def upgrade():
    op.add_column('chat_conversations', sa.Column(
        'stage', sa.String(10), nullable=False, server_default='new'))
    op.add_column('chat_conversations', sa.Column('result', sa.String(20)))
    op.add_column('chat_conversations', sa.Column(
        'archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_table(
        'chat_notes',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('author_id', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_chat_notes_conv', 'chat_notes', ['conversation_id', 'created_at'])
    op.create_table(
        'chat_scheduled',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('author_id', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('send_at', ts, nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='pending'),
        sa.Column('detail', sa.String(200)),
        sa.Column('message_id', BIG),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('pending','queued','cancelled')",
                           name='ck_chat_scheduled_status'),
    )
    op.create_index('ix_chat_scheduled_due', 'chat_scheduled', ['status', 'send_at'])
    op.create_table(
        'chat_consents',
        sa.Column('phone', sa.String(20), primary_key=True),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('note', sa.String(200)),
        sa.Column('changed_by', sa.String(255), nullable=False),
        sa.Column('changed_at', ts, nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('granted','revoked')", name='ck_chat_consents_status'),
    )
    op.create_table(
        'chat_quick_replies',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(80), nullable=False),
        sa.Column('shortcut', sa.String(30), nullable=False, unique=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by', sa.String(255)),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('chat_quick_replies')
    op.drop_table('chat_consents')
    op.drop_index('ix_chat_scheduled_due', table_name='chat_scheduled')
    op.drop_table('chat_scheduled')
    op.drop_index('ix_chat_notes_conv', table_name='chat_notes')
    op.drop_table('chat_notes')
    for name in ('archived', 'result', 'stage'):
        op.drop_column('chat_conversations', name)
