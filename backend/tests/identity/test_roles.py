"""Roles are assigned in Clerk and arrive inside the verified session. Portable SQL (SQLite)."""
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from livepulse.entrypoints.api import app
from livepulse.modules.analytics.models import RoleAudit, UserRole
from livepulse.modules.identity.roles import PERMISSIONS, screens_for
from livepulse.modules.social_live import models as m
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings
from livepulse.shared.db import Base, get_session

MKT = '/api/marketing/tiktok'
TABLES = [UserRole.__table__, RoleAudit.__table__, m.TiktokAccount.__table__,
          m.Tiktoker.__table__, m.Live.__table__, m.LiveComment.__table__,
          m.LiveEventKey.__table__, m.LiveInterestedUser.__table__, m.LiveMetrics.__table__,
          m.CapturedPhone.__table__, m.PhoneRegistry.__table__, m.ContactAudit.__table__]


def person(name, role=None):
    """A session whose Clerk Public metadata carries `role` (None = nothing assigned)."""
    return {'Authorization': f'Bearer user:{name}:{role or ""}'}


@pytest.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, 'admin_user_ids', ['boss'])
    monkeypatch.setattr(settings, 'social_live_token', 'ingest-secret')
    monkeypatch.setattr(settings, 'medical360_token', 'read-secret')
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        parts = token.split(':')
        uid, role = parts[1], (parts[2] if len(parts) > 2 else '')
        return {'id': uid, 'role': clerk.role_in({'livepulse': {'role': role}})}

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


EXPECTED = {
    'agente_ventas': ['agent'],
    'gerente': ['marketing'],
    'jefe_marketing': ['marketing'],
    'supervisor': ['agent', 'marketing'],
}


async def test_each_clerk_role_opens_exactly_its_views(env):
    client, _ = env
    assert (await client.get('/api/auth/me')).status_code == 401
    for role, screens in EXPECTED.items():
        me = (await client.get('/api/auth/me', headers=person('u_' + role, role))).json()
        assert me['role'] == role and me['screens'] == screens, role
        assert me['reason'] is None
    # The documented access table, as permissions.
    assert 'contacts:update' in PERMISSIONS['agente_ventas']
    assert 'read' not in PERMISSIONS['agente_ventas']
    assert {'read', 'export'} <= PERMISSIONS['gerente'] == PERMISSIONS['jefe_marketing']
    assert 'contacts:read' not in PERMISSIONS['gerente']
    assert {'contacts:read_all', 'contacts:assign_any'} <= PERMISSIONS['supervisor']
    assert screens_for(None) == []


async def test_a_person_without_a_clerk_role_has_no_access(env):
    client, _ = env
    me = (await client.get('/api/auth/me', headers=person('nuevo'))).json()
    assert me['role'] is None and me['screens'] == [] and me['permissions'] == []
    assert 'Clerk' in me['reason']
    # An unknown code is not a role (a typo grants nothing).
    typo = (await client.get('/api/auth/me', headers=person('typo', 'superadmin'))).json()
    assert typo['role'] is None and typo['screens'] == []
    for path in (f'{MKT}/overview', '/api/inbox', '/api/team'):
        res = await client.get(path, headers=person('nuevo'))
        assert res.status_code == 403, path
        assert 'rol' in res.json()['detail']


async def test_roles_come_from_clerk_not_from_our_database(env):
    client, factory = env
    # A stale/forged row in our own table grants nothing.
    async with factory() as s, s.begin():
        s.add(UserRole(user_id='falso', role='supervisor'))
    assert (await client.get(f'{MKT}/overview', headers=person('falso'))).status_code == 403
    # Clerk changes the role: the very next request follows it.
    assert (await client.get(f'{MKT}/overview', headers=person('ana', 'agente_ventas'))).status_code == 403
    assert (await client.get(f'{MKT}/overview', headers=person('ana', 'gerente'))).status_code == 200
    assert (await client.get('/api/inbox', headers=person('ana', 'gerente'))).status_code == 403
    # There is no API to assign roles any more: Clerk is the only place.
    assert (await client.put('/api/auth/users/ana/role', headers=person('boss'),
                             json={'role': 'gerente'})).status_code in (404, 405)
    assert (await client.get('/api/auth/users', headers=person('boss'))).status_code in (404, 405)


async def test_marketing_api_by_role_and_people_never_write_events(env):
    client, _ = env
    assert (await client.get(f'{MKT}/overview', headers=person('ana', 'agente_ventas'))
            ).status_code == 403
    for name, role in (('jefa', 'jefe_marketing'), ('gus', 'gerente'), ('sup', 'supervisor'),
                       ('boss', None)):
        res = await client.get(f'{MKT}/overview', headers=person(name, role))
        assert res.status_code == 200, (name, role)
    res = await client.post('/api/social-live/tiktokers', headers=person('boss'),
                            json={'id': 'x', 'name': 'X'})
    assert res.status_code == 403
    assert (await client.get(f'{MKT}/overview',
                             headers={'Authorization': 'Bearer read-secret'})).status_code == 200
    assert (await client.get(f'{MKT}/overview',
                             headers={'Authorization': 'Bearer garbage'})).status_code == 401


async def test_directory_remembers_names_for_the_team_list_but_never_decides_access(env):
    client, factory = env
    await client.get('/api/auth/me', headers=person('ana', 'agente_ventas'))
    await client.put('/api/auth/me/profile', headers=person('ana', 'agente_ventas'),
                     json={'name': 'Ana Ruiz'})
    await client.get('/api/auth/me', headers=person('sup', 'supervisor'))
    await client.get('/api/auth/me', headers=person('jefa', 'jefe_marketing'))
    async with factory() as s:
        rows = {r.user_id: (r.role, r.display_name)
                for r in (await s.scalars(select(UserRole))).all()}
    assert rows['ana'] == ('agente_ventas', 'Ana Ruiz')
    assert rows['sup'][0] == 'supervisor'
    team = (await client.get('/api/team', headers=person('sup', 'supervisor'))).json()['items']
    assert {t['name'] for t in team} == {'Ana Ruiz', 'sup'}  # marketing roles are not advisors
    # The directory follows a role change made in Clerk.
    await client.get('/api/auth/me', headers=person('ana', 'gerente'))
    team = (await client.get('/api/team', headers=person('sup', 'supervisor'))).json()['items']
    assert {t['id'] for t in team} == {'sup'}


def test_legacy_v1_sections_follow_the_clerk_role_too():
    """/v1 analytics routes use the same role; the old role-assignment routes are gone."""
    from fastapi.testclient import TestClient

    from livepulse.shared.auth import get_current_user

    def as_role(role):
        app.dependency_overrides[get_current_user] = lambda: {'id': 'u', 'role': role}
        return TestClient(app).get('/v1/capabilities').json()['role']

    try:
        assert as_role(None) is None
        assert as_role('agente_ventas') == 'care'
        assert as_role('gerente') == as_role('jefe_marketing') == 'marketing'
        assert as_role('supervisor') == 'admin'
        assert as_role('inventado') is None
        client = TestClient(app)
        assert client.put('/v1/staff/users/u/role', json={'role': 'care'}).status_code in (404, 405)
        assert client.get('/v1/staff/users').status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
