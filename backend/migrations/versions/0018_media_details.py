"""Kind, duration, name and size of WhatsApp attachments (audio, voice notes, video, documents,
stickers and images), so the screen can show them instead of a placeholder text. Additive only;
existing image messages are treated as images."""
import sqlalchemy as sa
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('media_kind', sa.String(10)))
    op.add_column('chat_messages', sa.Column('media_seconds', sa.Integer()))
    op.add_column('chat_messages', sa.Column('media_name', sa.String(200)))
    op.add_column('chat_messages', sa.Column('media_size', sa.Integer()))
    op.execute("UPDATE chat_messages SET media_kind = 'image' WHERE media_id IS NOT NULL")


def downgrade():
    for name in ('media_size', 'media_name', 'media_seconds', 'media_kind'):
        op.drop_column('chat_messages', name)
