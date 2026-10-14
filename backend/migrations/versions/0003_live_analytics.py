"""LIVE lifecycle, metrics, contacts and staff roles (immutable DDL snapshot)."""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_broadcast_room', 'broadcasts', ['account_id', 'room_id'])
    op.execute('\nCREATE TABLE leads (\n\tid VARCHAR(36) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\treview_needed BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE monitor_states (\n\taccount_id VARCHAR(32) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\tobserved_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\toffline_since TIMESTAMP WITH TIME ZONE, \n\tlast_error VARCHAR(120), \n\tPRIMARY KEY (account_id)\n)\n\n')
    op.execute('\nCREATE TABLE role_audit (\n\tid VARCHAR(36) NOT NULL, \n\tactor VARCHAR(255) NOT NULL, \n\tuser_id VARCHAR(255) NOT NULL, \n\trole VARCHAR(24) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('\nCREATE TABLE user_roles (\n\tuser_id VARCHAR(255) NOT NULL, \n\trole VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (user_id)\n)\n\n')
    op.execute('\nCREATE TABLE lead_aliases (\n\tuser_key VARCHAR(128) NOT NULL, \n\tlead_id VARCHAR(36) NOT NULL, \n\tusername VARCHAR(128), \n\tPRIMARY KEY (user_key), \n\tFOREIGN KEY(lead_id) REFERENCES leads (id)\n)\n\n')
    op.execute('CREATE INDEX ix_lead_aliases_lead_id ON lead_aliases (lead_id)')
    op.execute('\nCREATE TABLE lead_audit (\n\tid VARCHAR(36) NOT NULL, \n\tlead_id VARCHAR(36) NOT NULL, \n\tactor VARCHAR(255) NOT NULL, \n\taction VARCHAR(24) NOT NULL, \n\tprevious VARCHAR(24), \n\tvalue VARCHAR(24), \n\tnote TEXT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(lead_id) REFERENCES leads (id)\n)\n\n')
    op.execute('\nCREATE TABLE lead_phones (\n\tphone VARCHAR(20) NOT NULL, \n\tlead_id VARCHAR(36) NOT NULL, \n\tPRIMARY KEY (phone), \n\tFOREIGN KEY(lead_id) REFERENCES leads (id)\n)\n\n')
    op.execute('CREATE INDEX ix_lead_phones_lead_id ON lead_phones (lead_id)')
    op.execute('\nCREATE TABLE event_facts (\n\tevent_id VARCHAR(128) NOT NULL, \n\tbroadcast_id INTEGER NOT NULL, \n\taccount_id VARCHAR(32) NOT NULL, \n\tuser_key VARCHAR(128), \n\tkind VARCHAR(32) NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcomments INTEGER NOT NULL, \n\tlikes INTEGER NOT NULL, \n\tshares INTEGER NOT NULL, \n\tgifts INTEGER NOT NULL, \n\tdiamonds INTEGER NOT NULL, \n\tviewers INTEGER, \n\tinterested BOOLEAN NOT NULL, \n\tphones JSON NOT NULL, \n\tlead_id VARCHAR(36), \n\tPRIMARY KEY (event_id), \n\tFOREIGN KEY(event_id) REFERENCES raw_events (event_id), \n\tFOREIGN KEY(broadcast_id) REFERENCES broadcasts (id), \n\tFOREIGN KEY(lead_id) REFERENCES leads (id)\n)\n\n')
    op.execute('CREATE INDEX ix_event_facts_broadcast_id ON event_facts (broadcast_id)')


def downgrade():
    op.drop_table('event_facts')
    op.drop_table('lead_phones')
    op.drop_table('lead_audit')
    op.drop_table('lead_aliases')
    op.drop_table('user_roles')
    op.drop_table('role_audit')
    op.drop_table('monitor_states')
    op.drop_table('leads')
    op.drop_constraint('uq_broadcast_room', 'broadcasts', type_='unique')
