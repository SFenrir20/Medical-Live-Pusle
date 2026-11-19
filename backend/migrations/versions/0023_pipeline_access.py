"""Optional user allowlists for funnels; existing visibility is preserved by default."""
import sqlalchemy as sa
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crm_pipelines', sa.Column('allowed_user_ids', sa.JSON(), nullable=True))
    op.add_column('crm_pipelines', sa.Column('access_revision', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('crm_pipelines', sa.Column('access_updated_by', sa.String(255), nullable=True))
    op.add_column('crm_pipelines', sa.Column('access_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in ('access_updated_at', 'access_updated_by', 'access_revision', 'allowed_user_ids'):
        op.drop_column('crm_pipelines', name)
