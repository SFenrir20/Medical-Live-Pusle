"""Persistent MedicalClic and message preset configuration."""
import sqlalchemy as sa
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('automation_studio_settings',
                    sa.Column('id', sa.String(32), primary_key=True),
                    sa.Column('value', sa.JSON(), nullable=False),
                    sa.Column('updated_by', sa.String(255)),
                    sa.Column('updated_at', sa.DateTime(timezone=True),
                              nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table('automation_studio_settings')
