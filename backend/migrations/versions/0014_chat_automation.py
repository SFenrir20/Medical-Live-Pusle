"""Chat core (channels, conversations, messages, opt-outs) and the automation tools (flows, AI
agent, broadcasts, audit). Only adds tables; nothing existing changes. Flows, the AI agent and
broadcasts start disabled."""
import sqlalchemy as sa
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)
BIG = sa.BigInteger()


def now_default():
    return sa.text('now()')


def upgrade():
    op.create_table(
        'chat_channels',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('policy', sa.JSON(), nullable=False),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
        sa.CheckConstraint("kind IN ('simulator','whatsapp_mirror','whatsapp_cloud')",
                           name='ck_chat_channels_kind'),
        sa.CheckConstraint("status IN ('active','disabled')", name='ck_chat_channels_status'),
    )
    op.create_table(
        'chat_conversations',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.String(32), sa.ForeignKey('chat_channels.id'), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('contact_name', sa.String(128)),
        sa.Column('registry_id', BIG),
        sa.Column('advisor_id', sa.String(64)),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('bot_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('bot_paused_until', ts),
        sa.Column('bot_replies', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unread', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_inbound_at', ts),
        sa.Column('last_message_at', ts),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
        sa.UniqueConstraint('channel_id', 'phone', name='uq_chat_conversation_phone'),
    )
    op.create_index('ix_chat_conversations_last', 'chat_conversations', ['last_message_at'])
    op.create_table(
        'chat_messages',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('direction', sa.String(3), nullable=False),
        sa.Column('author_kind', sa.String(10), nullable=False),
        sa.Column('author_id', sa.String(255)),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('error', sa.String(200)),
        sa.Column('external_id', sa.String(128)),
        sa.Column('flow_run_id', BIG),
        sa.Column('broadcast_id', BIG),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
        sa.UniqueConstraint('conversation_id', 'external_id', name='uq_chat_message_external'),
        sa.CheckConstraint("direction IN ('in','out')", name='ck_chat_messages_direction'),
        sa.CheckConstraint("author_kind IN ('contact','agent','bot','system')",
                           name='ck_chat_messages_author'),
    )
    op.create_index('ix_chat_messages_conv', 'chat_messages', ['conversation_id', 'created_at'])
    op.create_index('ix_chat_messages_author', 'chat_messages', ['author_kind', 'created_at'])
    op.create_table(
        'chat_opt_outs',
        sa.Column('phone', sa.String(20), primary_key=True),
        sa.Column('reason', sa.String(200)),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
    )

    op.create_table(
        'automation_flows',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.String(300)),
        sa.Column('channel_id', sa.String(32), sa.ForeignKey('chat_channels.id'), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('graph', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by', sa.String(255)),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
        sa.Column('updated_at', ts, nullable=False, server_default=now_default()),
    )
    op.create_table(
        'automation_runs',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('flow_id', BIG, sa.ForeignKey('automation_flows.id'), nullable=False),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('current_node', sa.String(24)),
        sa.Column('resume_at', ts),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('steps_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('test', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('started_at', ts, nullable=False),
        sa.Column('finished_at', ts),
        sa.Column('reason', sa.String(300)),
        sa.CheckConstraint("status IN ('running','waiting','done','stopped','failed')",
                           name='ck_automation_runs_status'),
    )
    op.create_index('ix_automation_runs_due', 'automation_runs', ['status', 'resume_at'])
    op.create_index('ix_automation_runs_flow', 'automation_runs', ['flow_id', 'started_at'])
    op.create_table(
        'automation_steps',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('run_id', BIG, sa.ForeignKey('automation_runs.id'), nullable=False),
        sa.Column('node_id', sa.String(24), nullable=False),
        sa.Column('node_type', sa.String(32), nullable=False),
        sa.Column('outcome', sa.String(300), nullable=False),
        sa.Column('created_at', ts, nullable=False),
    )
    op.create_index('ix_automation_steps_run', 'automation_steps', ['run_id', 'id'])

    op.create_table(
        'ai_agent',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('provider', sa.String(20), nullable=False, server_default='echo'),
        sa.Column('model', sa.String(80), nullable=False, server_default=''),
        sa.Column('base_url', sa.String(200), nullable=False, server_default=''),
        sa.Column('api_key_encrypted', sa.Text()),
        sa.Column('name', sa.String(60), nullable=False, server_default='Asistente virtual'),
        sa.Column('clinic_name', sa.String(80), nullable=False, server_default='la clínica'),
        sa.Column('instructions', sa.Text(), nullable=False, server_default=''),
        sa.Column('knowledge_only', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('handoff_keywords', sa.JSON(), nullable=False),
        sa.Column('handoff_message', sa.String(300), nullable=False, server_default=''),
        sa.Column('max_replies', sa.Integer(), nullable=False, server_default='6'),
        sa.Column('daily_message_cap', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('updated_by', sa.String(255)),
        sa.Column('updated_at', ts, nullable=False, server_default=now_default()),
    )
    op.create_table(
        'ai_knowledge_docs',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
    )
    op.create_table(
        'ai_usage',
        sa.Column('day', sa.String(10), primary_key=True),
        sa.Column('messages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
    )

    op.create_table(
        'automation_broadcasts',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('channel_id', sa.String(32), sa.ForeignKey('chat_channels.id'), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('audience', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='draft'),
        sa.Column('scheduled_at', ts),
        sa.Column('pause_reason', sa.String(200)),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(255)),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
        sa.Column('started_at', ts),
        sa.Column('finished_at', ts),
        sa.CheckConstraint("status IN ('draft','scheduled','sending','paused','done','cancelled')",
                           name='ck_automation_broadcasts_status'),
    )
    op.create_table(
        'automation_broadcast_recipients',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('broadcast_id', BIG, sa.ForeignKey('automation_broadcasts.id'), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('name', sa.String(128)),
        sa.Column('status', sa.String(8), nullable=False, server_default='pending'),
        sa.Column('error', sa.String(200)),
        sa.Column('sent_at', ts),
        sa.UniqueConstraint('broadcast_id', 'phone', name='uq_broadcast_recipient'),
        sa.CheckConstraint("status IN ('pending','sent','failed','skipped')",
                           name='ck_broadcast_recipients_status'),
    )
    op.create_index('ix_broadcast_recipients_pending', 'automation_broadcast_recipients',
                    ['broadcast_id', 'status'])
    op.create_table(
        'automation_audit',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('actor', sa.String(255), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('entity', sa.String(30), nullable=False),
        sa.Column('entity_id', sa.String(40)),
        sa.Column('detail', sa.JSON()),
        sa.Column('created_at', ts, nullable=False, server_default=now_default()),
    )
    op.create_index('ix_automation_audit_created', 'automation_audit', ['created_at'])


def downgrade():
    for name in ('automation_audit', 'automation_broadcast_recipients', 'automation_broadcasts',
                 'ai_usage', 'ai_knowledge_docs', 'ai_agent', 'automation_steps',
                 'automation_runs', 'automation_flows', 'chat_opt_outs', 'chat_messages',
                 'chat_conversations', 'chat_channels'):
        op.drop_table(name)
