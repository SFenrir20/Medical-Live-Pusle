"""PostgreSQL acceptance tests for lifecycle, attribution, processing and staff access."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from livepulse.entrypoints.api import app
from livepulse.entrypoints.worker import process_batch
from livepulse.modules.analytics.models import EventFact, Lead, LeadAlias, LeadPhone, UserRole
from livepulse.modules.analytics.processor import handle_event
from livepulse.modules.analytics.reporting import attribution, lives
from livepulse.modules.broadcasts.lifecycle import BroadcastStore
from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.shifts.models import Shift
from livepulse.shared.auth import get_current_user
from livepulse.shared.config import settings
from livepulse.shared.db import Base, get_session

pytestmark = pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='PostgreSQL required')
T = datetime(2026, 10, 7, 19, tzinfo=timezone.utc)


@pytest.fixture
async def database(monkeypatch):
    schema = 'pipeline_' + uuid4().hex
    url = os.environ['DATABASE_URL']
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, 'admin_user_ids', ['boss'])
    monkeypatch.setattr(settings, 'medical360_token', 'server-secret')
    async def session():
        async with factory() as value:
            yield value
    def user(x_test_user: str = Header(default='ana')):
        return {'id': x_test_user, 'accounts': ['medical', 'medical-2']}
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_user] = user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield factory, client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_lifecycle_survives_restart_room_change_and_offline_grace(database):
    factory, _ = database
    store = BroadcastStore(factory)
    first = await store.connected('medical', 'room1', T)
    assert await BroadcastStore(factory).connected('medical', 'room1', T + timedelta(seconds=5)) == first
    async with store.lease('medical') as owned:
        assert owned
        async with store.lease('medical') as second:
            assert not second
    new = await store.connected('medical', 'room2', T + timedelta(hours=1))
    assert new != first
    await store.observed('medical', 'offline', T + timedelta(hours=2))
    await store.touch('medical', T + timedelta(hours=2, seconds=50))
    async with factory() as s:
        assert (await s.get(Broadcast, new)).ended_at is None
    await store.observed('medical', 'error', T + timedelta(hours=2, seconds=70), 'Timeout')
    await store.observed('medical', 'offline', T + timedelta(hours=2, seconds=130))
    async with factory() as s:
        assert (await s.get(Broadcast, new)).ended_at is None
    await store.observed('medical', 'offline', T + timedelta(hours=2, seconds=260))
    async with factory() as s:
        assert (await s.get(Broadcast, first)).end_confirmed is False
        assert (await s.get(Broadcast, new)).end_confirmed is True


async def test_pipeline_retries_contacts_metrics_and_boundary_attribution(database):
    factory, _ = database
    broadcast_id = await BroadcastStore(factory).connected('medical', 'room1', T)
    async with factory() as s, s.begin():
        broadcast = await s.get(Broadcast, broadcast_id)
        broadcast.ended_at = T + timedelta(hours=3, minutes=20)
        s.add_all([Shift(id='a', user_id='ana', account_id='medical', started_at=T,
                         ended_at=T + timedelta(hours=1), end_reason='handover', closed_by='bea'),
                   Shift(id='b', user_id='bea', account_id='medical', started_at=T + timedelta(hours=1),
                         ended_at=T + timedelta(hours=3), end_reason='manual', closed_by='bea')])
        for i, minute in enumerate([15, 60, 190]):
            s.add(RawEvent(event_id=f'e{i}', account_id='medical', broadcast_id=broadcast_id,
                          type='comment', occurred_at=T + timedelta(minutes=minute),
                          payload={'user': 'viewer1', 'username': 'lucia'},
                          raw_text='Me interesa, mi número es +51 987 654 321'))
        s.add(RawEvent(event_id='audience', account_id='medical', broadcast_id=broadcast_id,
                      type='audience', occurred_at=T, payload={'viewers': 50}))
        s.add(RawEvent(event_id='legacy', account_id='medical', type='comment',
                      occurred_at=T, payload={}, raw_text='old unlinked'))
    assert await process_batch(factory) == 4
    assert await process_batch(factory) == 0
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(Lead)) == 1
        assert await s.scalar(select(func.count()).select_from(LeadPhone)) == 1
        assert (await s.get(RawEvent, 'legacy')).processed_at is None
        report = (await lives(s))['items'][0]
        assert report['metrics']['comments'] == 3
        assert report['metrics']['interested_users'] == 1
        assert report['metrics']['peak_viewers'] == 50
        assert report['total_unique_viewers'] is None
        result = await attribution(s, broadcast_id)
        by_user = {r['user_id']: r['comments'] for r in result['by_user']}
        assert by_user == {'ana': 1, 'bea': 1, None: 1}
        assert result['intervals'][-1]['user_id'] is None
        assert result['intervals'][-1]['end'] - result['intervals'][-1]['start'] == timedelta(minutes=20)


async def test_failed_batch_rolls_back_and_retry_has_one_fact(database):
    factory, _ = database
    bid = await BroadcastStore(factory).connected('medical', 'room1', T)
    async with factory() as s, s.begin():
        s.add(RawEvent(event_id='e', account_id='medical', broadcast_id=bid,
                      type='comment', occurred_at=T, payload={'user': 'u'}, raw_text='precio'))
    with pytest.raises(RuntimeError):
        async with factory() as s, s.begin():
            await handle_event(s, 'e')
            raise RuntimeError('simulate crash before commit')
    async with factory() as s:
        assert await s.get(EventFact, 'e') is None
        assert (await s.get(RawEvent, 'e')).processed_at is None
    await asyncio.gather(process_batch(factory), process_batch(factory))
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(EventFact)) == 1


async def test_roles_and_leadsales_export_are_separated(database):
    factory, client = database
    assert (await client.get('/v1/capabilities')).json()['role'] == 'tiktoker'
    assert (await client.get('/v1/contacts')).status_code == 403
    assert (await client.get('/v1/analytics/lives')).status_code == 403
    assert (await client.get('/v1/integrations/medical360/lives')).status_code == 401
    assert (await client.get('/v1/integrations/medical360/lives',
                            headers={'X-Medical360-Token': 'server-secret'})).status_code == 200
    response = await client.put('/v1/staff/users/ana/role', json={'role': 'care'},
                                headers={'X-Test-User': 'boss'})
    assert response.status_code == 200
    assert (await client.get('/v1/analytics/lives')).status_code == 403
    contact = (await client.post('/v1/contacts/manual', json={'text': '+51 987654321',
                                                           'username': '=FORMULA()'})).json()
    assert (await client.post('/v1/contacts/manual', json={'text': '987654321',
                                                         'username': 'another'})).json()['id'] == contact['id']
    ready = await client.patch('/v1/contacts/' + contact['id'],
                               json={'status': 'ready', 'expected_status': 'new'})
    assert ready.status_code == 200
    exported = (await client.post('/v1/contacts/export/leadsales')).json()['csv']
    assert exported.startswith('Area code,Phone,Name,Value,Email,Tags,Company,Assignee')
    assert '51,987654321' in exported and "'=FORMULA()" in exported
    assert len(exported.splitlines()) == 2
    assert (await client.patch('/v1/contacts/' + contact['id'],
        json={'status': 'closed', 'expected_status': 'new'})).status_code == 409
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(Lead)) == 1
        assert await s.scalar(select(func.count()).select_from(LeadAlias)) == 2
        assert (await s.get(UserRole, 'ana')).role == 'care'
