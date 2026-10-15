"""Keep viewer deduplication after comment retention."""
import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'live_interested_users',
        sa.Column('live_id', sa.String(40), sa.ForeignKey('lives.id'), primary_key=True),
        sa.Column('username', sa.String(128), primary_key=True),
    )
    # Seed existing detail without incrementing counters already consolidated.
    op.execute("""
        INSERT INTO live_interested_users (live_id, username)
        SELECT DISTINCT live_id, username FROM live_comments WHERE interested
        ON CONFLICT DO NOTHING
    """)
    # Recover identities from published historical events whose comments were purged.
    # Unpublished events will populate the registry through the worker as usual.
    op.execute("""
        INSERT INTO live_interested_users (live_id, username)
        SELECT DISTINCT l.id,
            LEFT(BTRIM(COALESCE(NULLIF(r.payload->>'username', ''),
                                NULLIF(r.payload->>'nickname', ''),
                                r.payload->>'user')), 128)
        FROM raw_events r
        JOIN event_facts f ON f.event_id = r.event_id
        JOIN lives l ON l.id = 'TT-' || r.broadcast_id::text
        WHERE r.published_at IS NOT NULL AND f.interested
          AND BTRIM(COALESCE(NULLIF(r.payload->>'username', ''),
                            NULLIF(r.payload->>'nickname', ''),
                            r.payload->>'user', '')) <> ''
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table('live_interested_users')
