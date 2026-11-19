"""Execute the real upgrade on existing data, including advanced cards and LIVE status precedence."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


@pytest.mark.parametrize('ambiguous', [False, True])
def test_upgrade_adopts_only_unambiguous_citas_and_backfills_missing_members(ambiguous):
    path = Path(__file__).parents[2] / 'migrations/versions/0024_qualified_funnel.py'
    spec = importlib.util.spec_from_file_location('qualified_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        for statement in (
            'CREATE TABLE crm_pipelines (id INTEGER PRIMARY KEY, name TEXT, key TEXT, archived BOOLEAN, site_id INTEGER)',
            'CREATE TABLE crm_pipeline_stages (id INTEGER PRIMARY KEY, pipeline_id INTEGER, name TEXT, position INTEGER)',
            'CREATE TABLE chat_conversations (id INTEGER PRIMARY KEY, phone TEXT, stage TEXT)',
            'CREATE TABLE phone_registry (id INTEGER PRIMARY KEY, phone TEXT, status TEXT)',
            '''CREATE TABLE crm_pipeline_cards (id INTEGER PRIMARY KEY, pipeline_id INTEGER,
                conversation_id INTEGER, stage_id INTEGER, value_cents INTEGER, entered_at TEXT, updated_by TEXT,
                UNIQUE(pipeline_id, conversation_id))''',
            '''CREATE TABLE crm_pipeline_events (id INTEGER PRIMARY KEY, pipeline_id INTEGER,
                conversation_id INTEGER, to_stage_id INTEGER, actor_id TEXT, at TEXT)''',
            "INSERT INTO crm_pipelines VALUES (1, 'Citas', NULL, false, NULL), (2, 'Sede', NULL, false, 1)",
            "INSERT INTO crm_pipeline_stages VALUES (10, 1, 'Cita', 0), (11, 1, 'Operado', 1)",
            "INSERT INTO chat_conversations VALUES (1, 'a', 'qualified'), (2, 'b', 'new'), (3, 'c', 'qualified'), (4, 'd', 'qualified')",
            "INSERT INTO phone_registry VALUES (1, 'b', 'qualified'), (2, 'c', 'new')",
            "INSERT INTO crm_pipeline_cards VALUES (1, 1, 4, 11, 999, 'original', 'ana')",
        ):
            connection.execute(text(statement))
        if ambiguous:
            connection.execute(text("INSERT INTO crm_pipelines VALUES (3, ' Citas ', NULL, false, NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        rows = connection.execute(text('SELECT conversation_id, stage_id, value_cents FROM crm_pipeline_cards '
                                       'ORDER BY conversation_id')).all()
        assert rows == ([(4, 11, 999)] if ambiguous else [(1, 10, 0), (2, 10, 0), (4, 11, 999)])
        assert connection.scalar(text('SELECT count(*) FROM crm_pipeline_events')) == (0 if ambiguous else 2)
        assert connection.scalar(text('SELECT auto_qualified FROM crm_pipelines WHERE id=2')) == 0
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.scalar(text('SELECT count(*) FROM crm_pipeline_cards')) == len(rows)
    engine.dispose()
