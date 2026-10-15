"""Medical Social Live integration: lives, metrics, temporary comments and captured phones
(immutable DDL snapshot)."""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TABLE tiktok_accounts (\n\tid VARCHAR(32) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tusername VARCHAR(64) NOT NULL, \n\ttype VARCHAR(32) DEFAULT 'live' NOT NULL, \n\tactive BOOLEAN DEFAULT true NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (username)\n)")
    op.execute('CREATE TABLE tiktokers (\n\tid VARCHAR(64) NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tactive BOOLEAN DEFAULT true NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id)\n)')
    op.execute("CREATE TABLE lives (\n\tid VARCHAR(40) NOT NULL, \n\ttiktoker_id VARCHAR(64) NOT NULL, \n\taccount_id VARCHAR(32) NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tended_at TIMESTAMP WITH TIME ZONE, \n\tduration_seconds INTEGER, \n\tstatus VARCHAR(16) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_lives_status CHECK (status IN ('scheduled','live','finished','cancelled')), \n\tCONSTRAINT ck_lives_time CHECK (ended_at IS NULL OR ended_at >= started_at), \n\tFOREIGN KEY(tiktoker_id) REFERENCES tiktokers (id), \n\tFOREIGN KEY(account_id) REFERENCES tiktok_accounts (id)\n)")
    op.execute('CREATE INDEX ix_lives_account ON lives (account_id, started_at)')
    op.execute('CREATE INDEX ix_lives_started ON lives (started_at)')
    op.execute('CREATE INDEX ix_lives_tiktoker ON lives (tiktoker_id, started_at)')
    op.execute('CREATE TABLE live_comments (\n\tid BIGSERIAL NOT NULL, \n\tlive_id VARCHAR(40) NOT NULL, \n\tusername VARCHAR(128) NOT NULL, \n\tcomment TEXT NOT NULL, \n\tphone_detected VARCHAR(20), \n\tinterested BOOLEAN DEFAULT false NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(live_id) REFERENCES lives (id)\n)')
    op.execute('CREATE INDEX ix_live_comments_created ON live_comments (created_at)')
    op.execute('CREATE INDEX ix_live_comments_live_created ON live_comments (live_id, created_at)')
    op.execute('CREATE INDEX ix_live_comments_live_username ON live_comments (live_id, username)')
    op.execute('CREATE TABLE live_event_keys (\n\tlive_id VARCHAR(40) NOT NULL, \n\tevent_id VARCHAR(128) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (live_id, event_id), \n\tFOREIGN KEY(live_id) REFERENCES lives (id)\n)')
    op.execute('CREATE INDEX ix_live_event_keys_created ON live_event_keys (created_at)')
    op.execute("CREATE TABLE live_metrics (\n\tid SERIAL NOT NULL, \n\tlive_id VARCHAR(40) NOT NULL, \n\tviews INTEGER DEFAULT '0' NOT NULL, \n\tunique_viewers INTEGER DEFAULT '0' NOT NULL, \n\tcomments_count INTEGER DEFAULT '0' NOT NULL, \n\tlikes_count INTEGER DEFAULT '0' NOT NULL, \n\tshares_count INTEGER DEFAULT '0' NOT NULL, \n\tnew_followers INTEGER DEFAULT '0' NOT NULL, \n\tdonations_count INTEGER DEFAULT '0' NOT NULL, \n\tdirect_messages_count INTEGER DEFAULT '0' NOT NULL, \n\tinterested_viewers INTEGER DEFAULT '0' NOT NULL, \n\tphones_captured INTEGER DEFAULT '0' NOT NULL, \n\tleads_per_hour FLOAT DEFAULT '0' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (live_id), \n\tFOREIGN KEY(live_id) REFERENCES lives (id)\n)")
    op.execute("CREATE TABLE captured_phones (\n\tid BIGSERIAL NOT NULL, \n\tlive_id VARCHAR(40) NOT NULL, \n\tphone VARCHAR(20) NOT NULL, \n\ttiktok_username VARCHAR(128), \n\tsource VARCHAR(24) NOT NULL, \n\tcaptured_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcontacted_at TIMESTAMP WITH TIME ZONE, \n\tadvisor_id VARCHAR(64), \n\tstatus VARCHAR(16) DEFAULT 'new' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_captured_phone_live UNIQUE (live_id, phone), \n\tCONSTRAINT ck_captured_phones_status CHECK (status IN ('new','contacted','qualified','discarded')), \n\tCONSTRAINT ck_captured_phones_source CHECK (source IN ('comment','manual_capture','direct_message','speech','other')), \n\tCONSTRAINT ck_captured_phones_contact_time CHECK (contacted_at IS NULL OR contacted_at >= captured_at), \n\tFOREIGN KEY(live_id) REFERENCES lives (id)\n)")
    op.execute('CREATE INDEX ix_captured_phones_captured ON captured_phones (captured_at)')
    op.execute('CREATE INDEX ix_captured_phones_status ON captured_phones (status, captured_at)')


def downgrade():
    op.drop_table('captured_phones')
    op.drop_table('live_metrics')
    op.drop_table('live_event_keys')
    op.drop_table('live_comments')
    op.drop_table('lives')
    op.drop_table('tiktokers')
    op.drop_table('tiktok_accounts')
