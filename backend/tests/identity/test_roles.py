"""Clerk-authenticated people and the four business roles. Portable SQL (SQLite)."""
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from livepulse.entrypoints.api import app
from livepulse.modules.analytics.models import RoleAudit, UserRole
from livepulse.modules.social_live import models as m
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings
from livepulse.shared.db import Base, get_session

MKT = '/api/marketing/tiktok'
TABLES = [UserRole.__table__, RoleAudit.__table__, m.TiktokAccount.__table__,
          m.Tiktoker.__table__, m.Live.__table__, m.LiveComment.__table__,
          m.LiveEventKey.__table__, m.LiveInterestedUser.__table__, m.LiveMetrics.__table__, m.CapturedPhone.__table__,
          m.PhoneRegistry.__table__, m.ContactAudit.__table__]


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


@pytest.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, 'admin_user_ids', ['boss'])
    monkeypatch.setattr(settings, 'social_live_token', 'ingest-secret')
    monkeypatch.setattr(settings, 'medical360_token', 'read-secret')
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        return {'id': token.removeprefix('user:'), 'accounts': [], 'status': 'approved'}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool,
                                 connect_args={'check_same_thread': False})
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        async with factory() as value:
            yield value

    app.dependency_overrides[get_session] = session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_first_sign_in_is_least_privileged_and_screens_follow_role(env):
    client, _ = env
    assert (await client.get('/api/auth/me')).status_code == 401
    me = (await client.get('/api/auth/me', headers=person('ana'))).json()
    assert me['role'] == 'agente_ventas' and me['screens'] == ['agent']
    assert me['can_manage_roles'] is False
    boss = (await client.get('/api/auth/me', headers=person('boss'))).json()
    assert boss['role'] == 'admin' and boss['screens'] == ['agent', 'marketing']
    assert boss['can_manage_roles'] is True


async def test_admin_assigns_the_four_roles_and_screens_change(env):
    client, _ = env
    for name in ('ana', 'gus', 'jefa', 'sup'):
        await client.get('/api/auth/me', headers=person(name))
    assert (await client.put('/api/auth/users/ana/role', headers=person('gus'),
                             json={'role': 'gerente'})).status_code == 403
    expected = {'ana': ('agente_ventas', ['agent']), 'gus': ('gerente', ['marketing']),
                'jefa': ('jefe_marketing', ['marketing']),
                'sup': ('supervisor', ['agent', 'marketing'])}
    for name, (role, _) in expected.items():
        res = await client.put(f'/api/auth/users/{name}/role', headers=person('boss'),
                               json={'role': role})
        assert res.status_code == 200, res.text
    for name, (role, screens) in expected.items():
        me = (await client.get('/api/auth/me', headers=person(name))).json()
        assert (me['role'], me['screens']) == (role, screens)
    assert (await client.put('/api/auth/users/ana/role', headers=person('boss'),
                             json={'role': 'dios'})).status_code == 422
    assert (await client.put('/api/auth/users/boss/role', headers=person('boss'),
                             json={'role': 'gerente'})).status_code == 409
    assert (await client.put('/api/auth/users/nobody/role', headers=person('boss'),
                             json={'role': 'gerente'})).status_code == 404
    listing = (await client.get('/api/auth/users', headers=person('boss'))).json()
    assert {i['id']: i['role'] for i in listing['items']}['sup'] == 'supervisor'


async def test_marketing_api_accepts_people_by_role_and_never_ingest(env):
    client, _ = env
    for name in ('ana', 'jefa', 'sup'):
        await client.get('/api/auth/me', headers=person(name))
    await client.put('/api/auth/users/jefa/role', headers=person('boss'),
                     json={'role': 'jefe_marketing'})
    await client.put('/api/auth/users/sup/role', headers=person('boss'),
                     json={'role': 'supervisor'})
    # Sales agents cannot read marketing statistics or export.
    assert (await client.get(f'{MKT}/overview', headers=person('ana'))).status_code == 403
    for name in ('jefa', 'sup', 'boss'):
        assert (await client.get(f'{MKT}/overview', headers=person(name))).status_code == 200
    # People never write through the service ingestion API.
    res = await client.post('/api/social-live/tiktokers', headers=person('boss'),
                            json={'id': 'x', 'name': 'X'})
    assert res.status_code == 403
    # Service tokens keep working, and a forged session is rejected.
    assert (await client.get(f'{MKT}/overview',
                             headers={'Authorization': 'Bearer read-secret'})).status_code == 200
    assert (await client.get(f'{MKT}/overview',
                             headers={'Authorization': 'Bearer garbage'})).status_code == 401
