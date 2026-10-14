"""Name shown in Medical 360 for the person in charge of a shift."""
import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shifts', sa.Column('display_name', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('shifts', 'display_name')
