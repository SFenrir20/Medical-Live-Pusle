"""WhatsApp mirror inbox, durable outbox and delivery evidence (additive)."""
import sqlalchemy as sa
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('wa_request_id', sa.String(36)))
    op.create_unique_constraint('uq_chat_messages_wa_request_id', 'chat_messages', ['wa_request_id'])
    for name in ('sent_at', 'delivered_at', 'read_at', 'observed_at'):
        op.add_column('chat_messages', sa.Column(name, sa.DateTime(timezone=True)))
    op.create_index('ix_chat_messages_sent', 'chat_messages', ['conversation_id', 'sent_at'])
    op.create_table('wa_events', sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                              server_default=sa.func.now()))
    op.create_table('wa_receipts', sa.Column('external_id', sa.String(128), primary_key=True),
                    sa.Column('phone', sa.String(20), nullable=False),
                    sa.Column('sent_at', sa.DateTime(timezone=True)),
                    sa.Column('delivered_at', sa.DateTime(timezone=True)),
                    sa.Column('read_at', sa.DateTime(timezone=True)),
                    sa.Column('delivered_clock', sa.String(16)),
                    sa.Column('read_clock', sa.String(16)))


def downgrade():
    op.drop_index('ix_chat_messages_sent', table_name='chat_messages')
    op.drop_table('wa_receipts')
    op.drop_table('wa_events')
    op.drop_constraint('uq_chat_messages_wa_request_id', 'chat_messages', type_='unique')
    for name in ('wa_request_id', 'sent_at', 'delivered_at', 'read_at', 'observed_at'):
        op.drop_column('chat_messages', name)
