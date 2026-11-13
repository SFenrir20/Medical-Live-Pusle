"""Mark imported history so replays/receipts cannot trigger current CRM workflows."""
import sqlalchemy as sa
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('historical', sa.Boolean(), nullable=False,
                                           server_default=sa.text('false')))


def downgrade():
    op.drop_column('chat_messages', 'historical')
