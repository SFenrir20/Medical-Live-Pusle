"""Responsible of a live from the code in its title; TikToker roster.

Non-destructive: only adds columns and the six TikTokers. Lives already assigned by hand keep
their responsible and are marked as manual, so the title never overrides them.
"""
import sqlalchemy as sa
from alembic import context, op

from livepulse.modules.social_live.roster import seed_roster

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tiktokers', sa.Column('code', sa.String(8), nullable=True))
    op.add_column('tiktokers', sa.Column('full_name', sa.String(100), nullable=True))
    op.create_unique_constraint('tiktokers_code_key', 'tiktokers', ['code'])
    op.add_column('lives', sa.Column('title', sa.String(200), nullable=True))
    op.add_column('lives', sa.Column('responsible_source', sa.String(12), nullable=True))
    op.add_column('broadcasts', sa.Column('title', sa.String(200), nullable=True))
    op.execute("UPDATE lives SET responsible_source = 'manual' WHERE tiktoker_id IS NOT NULL")
    if not context.is_offline_mode():  # `alembic ... --sql` only renders the schema
        seed_roster(op.get_bind())


def downgrade():
    op.drop_column('broadcasts', 'title')
    op.drop_column('lives', 'responsible_source')
    op.drop_column('lives', 'title')
    op.drop_constraint('tiktokers_code_key', 'tiktokers', type_='unique')
    op.drop_column('tiktokers', 'full_name')
    op.drop_column('tiktokers', 'code')
