"""Alerts for contacts that re-send their number after being contacted, "no me contactan"
comments, and the audit of contact-list downloads. Only adds structure; no data is changed."""
import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    ts = sa.DateTime(timezone=True)
    op.add_column('live_comments', sa.Column(
        'complaint', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('live_comments', sa.Column('complaint_reviewed_by', sa.String(255)))
    op.add_column('live_comments', sa.Column('complaint_reviewed_at', ts))
    op.create_index('ix_live_comments_complaint', 'live_comments', ['complaint', 'created_at'])

    op.create_table(
        'contact_alerts',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('registry_id', sa.BigInteger(), sa.ForeignKey('phone_registry.id'),
                  nullable=False),
        sa.Column('live_id', sa.String(40), sa.ForeignKey('lives.id'), nullable=False),
        sa.Column('account_id', sa.String(32)),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('comment_at', ts, nullable=False),
        sa.Column('contacted_at', ts, nullable=False),
        sa.Column('advisor_id', sa.String(64)),
        sa.Column('repeats', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_seen_at', ts, nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='open'),
        sa.Column('reviewed_by', sa.String(255)),
        sa.Column('reviewed_at', ts),
        sa.Column('note', sa.String(500)),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('registry_id', 'live_id', name='uq_contact_alert_live'),
        sa.CheckConstraint("kind IN ('same_live','other_live','other_account')",
                           name='ck_contact_alerts_kind'),
        sa.CheckConstraint("status IN ('open','reviewed','dismissed')",
                           name='ck_contact_alerts_status'),
    )
    op.create_index('ix_contact_alerts_status', 'contact_alerts', ['status', 'created_at'])
    op.create_table(
        'export_audit',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('actor', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('rows', sa.Integer(), nullable=False),
        sa.Column('created_at', ts, nullable=False, server_default=sa.text('now()')),
    )


def downgrade():
    op.drop_table('export_audit')
    op.drop_index('ix_contact_alerts_status', table_name='contact_alerts')
    op.drop_table('contact_alerts')
    op.drop_index('ix_live_comments_complaint', table_name='live_comments')
    op.drop_column('live_comments', 'complaint_reviewed_at')
    op.drop_column('live_comments', 'complaint_reviewed_by')
    op.drop_column('live_comments', 'complaint')
