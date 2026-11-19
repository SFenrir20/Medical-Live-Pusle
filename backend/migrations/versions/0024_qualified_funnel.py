"""Automatic entry of scheduled contacts into the existing Citas funnel."""
import sqlalchemy as sa
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

# Same source of truth as Contactos: the LIVE registry wins over the chat's local stage.
# Only missing memberships are added; advanced cards are never moved backwards.
CANDIDATES = """
SELECT p.id AS pipeline_id, c.id AS conversation_id, s.id AS stage_id
FROM crm_pipelines p
JOIN crm_pipeline_stages s ON s.pipeline_id = p.id
CROSS JOIN chat_conversations c
LEFT JOIN phone_registry r ON r.phone = c.phone
WHERE p.auto_qualified = true AND p.archived = false AND p.site_id IS NULL
  AND s.id = (SELECT st.id FROM crm_pipeline_stages st
              WHERE st.pipeline_id = p.id ORDER BY st.position, st.id LIMIT 1)
  AND (CASE WHEN r.id IS NOT NULL THEN r.status ELSE c.stage END) = 'qualified'
  AND NOT EXISTS (SELECT 1 FROM crm_pipeline_cards pc
                  WHERE pc.pipeline_id = p.id AND pc.conversation_id = c.id)
"""


def upgrade():
    op.add_column('crm_pipelines', sa.Column('auto_qualified', sa.Boolean(), nullable=False,
                                            server_default=sa.false()))
    # Adopt only an unambiguous existing global Citas -> Cita funnel. Other installations
    # can opt in explicitly in Configuración; no display-name dependency remains afterwards.
    op.execute("""
UPDATE crm_pipelines SET auto_qualified = true
WHERE id = (SELECT min(p.id) FROM crm_pipelines p
            WHERE lower(trim(p.name)) = 'citas' AND p.archived = false
              AND p.site_id IS NULL AND p.key IS NULL
            HAVING count(*) = 1)
  AND (SELECT lower(trim(s.name)) FROM crm_pipeline_stages s
       WHERE s.pipeline_id = crm_pipelines.id ORDER BY s.position, s.id LIMIT 1) = 'cita'
""")
    op.execute("""
INSERT INTO crm_pipeline_events (pipeline_id, conversation_id, to_stage_id, actor_id, at)
SELECT pipeline_id, conversation_id, stage_id, 'system:qualified', CURRENT_TIMESTAMP
FROM (""" + CANDIDATES + ') candidates')
    op.execute("""
INSERT INTO crm_pipeline_cards (pipeline_id, conversation_id, stage_id, value_cents, entered_at, updated_by)
SELECT pipeline_id, conversation_id, stage_id, 0, CURRENT_TIMESTAMP, 'system:qualified'
FROM (""" + CANDIDATES + ') candidates')


def downgrade():
    # Keep memberships and their audit; removing this feature must not lose clinical follow-up.
    op.drop_column('crm_pipelines', 'auto_qualified')
