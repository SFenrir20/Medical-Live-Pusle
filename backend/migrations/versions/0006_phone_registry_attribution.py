"""Single contact registry, audit trail, honest audience metrics and read-model publication.

Data-preserving: nothing is dropped before its content was copied to the new structure.
  - phone_registry: one contact per number (first capture); built from captured_phones and from
    the previous analytics leads, then captured_phones keeps only appearances.
  - live_metrics: concurrent-viewer samples (peak/average) replace the mislabeled
    "unique viewers"; unique_viewers becomes NULL = not available.
  - raw_events.published_at: permanent marker, so history is converted exactly once.
"""
import sqlalchemy as sa
from alembic import context, op

from livepulse.modules.social_live import backfill

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    ts = sa.DateTime(timezone=True)
    now = sa.text('now()')

    op.create_table(
        'phone_registry',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('phone', sa.String(20), nullable=False, unique=True),
        sa.Column('first_live_id', sa.String(40), sa.ForeignKey('lives.id')),
        sa.Column('first_account_id', sa.String(32)),
        sa.Column('first_captured_at', ts, nullable=False),
        sa.Column('first_username', sa.String(128)),
        sa.Column('first_source', sa.String(24), nullable=False, server_default='comment'),
        sa.Column('status', sa.String(16), nullable=False, server_default='new'),
        sa.Column('advisor_id', sa.String(64)),
        sa.Column('assigned_at', ts),
        sa.Column('contacted_at', ts),
        sa.Column('created_at', ts, nullable=False, server_default=now),
        sa.Column('updated_at', ts, nullable=False, server_default=now),
        sa.CheckConstraint("status IN ('new','contacted','qualified','discarded')",
                           name='ck_phone_registry_status'),
        sa.CheckConstraint('contacted_at IS NULL OR contacted_at >= first_captured_at',
                           name='ck_phone_registry_contact_time'),
    )
    op.create_index('ix_phone_registry_captured', 'phone_registry', ['first_captured_at'])
    op.create_index('ix_phone_registry_advisor', 'phone_registry', ['advisor_id', 'status'])
    op.create_table(
        'contact_audit',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('registry_id', sa.BigInteger(), sa.ForeignKey('phone_registry.id'),
                  nullable=False),
        sa.Column('actor', sa.String(255), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('previous', sa.String(64)),
        sa.Column('value', sa.String(64)),
        sa.Column('created_at', ts, nullable=False, server_default=now),
    )
    op.create_index('ix_contact_audit_registry', 'contact_audit', ['registry_id', 'created_at'])

    op.add_column('raw_events', sa.Column('published_at', ts, nullable=True))
    op.create_index('ix_raw_events_published', 'raw_events', ['published_at', 'occurred_at'])
    for name in ('peak_viewers', 'viewer_samples', 'phone_mentions'):
        op.add_column('live_metrics', sa.Column(
            name, sa.Integer(), nullable=False, server_default='0'))
    op.add_column('live_metrics', sa.Column(
        'viewer_sum', sa.BigInteger(), nullable=False, server_default='0'))
    op.alter_column('live_metrics', 'unique_viewers', existing_type=sa.Integer(),
                    nullable=True, server_default=None)
    # A live is not owned by one TikToker: who worked comes from shifts, by time.
    op.alter_column('lives', 'tiktoker_id', existing_type=sa.String(64), nullable=True)
    op.add_column('captured_phones', sa.Column(
        'is_new', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('user_roles', sa.Column('display_name', sa.String(100), nullable=True))

    # ---- data ------------------------------------------------------------------------
    # What was stored as "unique viewers" was the highest concurrent sample.
    op.execute('UPDATE live_metrics SET peak_viewers = unique_viewers, unique_viewers = NULL '
               'WHERE unique_viewers IS NOT NULL')
    if not context.is_offline_mode():  # `alembic ... --sql` only renders the schema
        backfill.convert_all(op.get_bind())

    # ---- appearances keep only appearance data ----------------------------------------
    for column in ('status', 'advisor_id', 'contacted_at', 'updated_at'):
        op.drop_column('captured_phones', column)  # its constraints/indexes go with it
    op.create_foreign_key('fk_captured_phones_phone', 'captured_phones', 'phone_registry',
                          ['phone'], ['phone'])
    op.create_index('ix_captured_phones_phone', 'captured_phones', ['phone'])


def downgrade():
    ts = sa.DateTime(timezone=True)
    op.drop_index('ix_captured_phones_phone', table_name='captured_phones')
    op.drop_constraint('fk_captured_phones_phone', 'captured_phones', type_='foreignkey')
    op.add_column('captured_phones', sa.Column(
        'status', sa.String(16), nullable=False, server_default='new'))
    op.add_column('captured_phones', sa.Column('advisor_id', sa.String(64)))
    op.add_column('captured_phones', sa.Column('contacted_at', ts))
    op.add_column('captured_phones', sa.Column(
        'updated_at', ts, nullable=False, server_default=sa.text('now()')))
    # Attention state goes back to the first appearance of each contact.
    op.execute(
        'UPDATE captured_phones c SET status = r.status, advisor_id = r.advisor_id, '
        'contacted_at = r.contacted_at FROM phone_registry r '
        'WHERE r.phone = c.phone AND c.is_new')
    op.drop_column('user_roles', 'display_name')
    op.drop_column('captured_phones', 'is_new')
    op.execute('UPDATE live_metrics SET unique_viewers = peak_viewers')
    op.execute('UPDATE live_metrics SET unique_viewers = 0 WHERE unique_viewers IS NULL')
    op.alter_column('live_metrics', 'unique_viewers', existing_type=sa.Integer(),
                    nullable=False, server_default='0')
    for name in ('viewer_sum', 'phone_mentions', 'viewer_samples', 'peak_viewers'):
        op.drop_column('live_metrics', name)
    op.drop_index('ix_raw_events_published', table_name='raw_events')
    op.drop_column('raw_events', 'published_at')
    op.drop_table('contact_audit')
    op.drop_table('phone_registry')
