"""Funnels (embudos): pipelines, their stages, the conversations inside them and the moves between
stages. Additive only; the built-in funnel is created on first use and mirrors the contact status."""
import sqlalchemy as sa
from alembic import op

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)
BIG = sa.BigInteger()


def upgrade():
    op.create_table(
        'crm_pipelines',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(20), unique=True),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_by', sa.String(255)),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )
    op.create_table(
        'crm_pipeline_stages',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('pipeline_id', BIG, sa.ForeignKey('crm_pipelines.id'), nullable=False),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('color', sa.String(7), nullable=False, server_default='#0f92ac'),
        sa.Column('description', sa.String(200)),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('legacy_stage', sa.String(10)),
    )
    op.create_index('ix_crm_stage_pipeline', 'crm_pipeline_stages', ['pipeline_id', 'position'])
    op.create_table(
        'crm_pipeline_cards',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('pipeline_id', BIG, sa.ForeignKey('crm_pipelines.id'), nullable=False),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('stage_id', BIG, sa.ForeignKey('crm_pipeline_stages.id')),
        sa.Column('value_cents', BIG, nullable=False, server_default='0'),
        sa.Column('entered_at', ts, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by', sa.String(255)),
    )
    op.create_index('ux_crm_card', 'crm_pipeline_cards', ['pipeline_id', 'conversation_id'], unique=True)
    op.create_index('ix_crm_card_stage', 'crm_pipeline_cards', ['stage_id'])
    op.create_table(
        'crm_pipeline_events',
        sa.Column('id', BIG, primary_key=True, autoincrement=True),
        sa.Column('pipeline_id', BIG, sa.ForeignKey('crm_pipelines.id'), nullable=False),
        sa.Column('conversation_id', BIG, sa.ForeignKey('chat_conversations.id'), nullable=False),
        sa.Column('from_stage_id', BIG),
        sa.Column('to_stage_id', BIG, nullable=False),
        sa.Column('actor_id', sa.String(255), nullable=False),
        sa.Column('at', ts, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_crm_event_stage', 'crm_pipeline_events',
                    ['pipeline_id', 'to_stage_id', 'conversation_id'])


def downgrade():
    for table in ('crm_pipeline_events', 'crm_pipeline_cards', 'crm_pipeline_stages', 'crm_pipelines'):
        op.drop_table(table)
