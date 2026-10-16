"""The code a TikToker writes in the live title tells the system who is on air."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from livepulse.entrypoints.monitor import extract_title
from livepulse.modules.analytics.models import UserRole
from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.social_live import models as m
from livepulse.modules.social_live import titles
from livepulse.modules.social_live.publisher import publish_batch
from livepulse.modules.social_live.roster import ROSTER, seed_roster
from livepulse.shared import auth as clerk

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, MKT = '/api/social-live', '/api/marketing/tiktok'
CODES = {row['code']: row['id'] for row in ROSTER}


# ---------- reading the title ----------

@pytest.mark.parametrize('title,expected', [
    ('Cirugías en vivo A1', 'TK-A01'),
    ('[m2] consultas', 'TK-M02'),
    ('L3-LIVE de hoy', 'TK-L03'),
    ('Con Briggite b4 🔥', 'TK-B04'),
    ('F5', 'TK-F05'),
    ('Rinoplastia (N6)', 'TK-N06'),
    ('A1 A1 otra vez', 'TK-A01'),            # the same code twice is still one person
])
def test_a_single_known_code_identifies_the_tiktoker(title, expected):
    assert titles.resolve(title, CODES) == (expected, 'matched')


@pytest.mark.parametrize('title', [
    None, '', 'Cirugías estéticas', 'MA1 promo', 'A12 semanas', 'A1B', 'X9 en vivo', '1A', 'Vitamina',
])
def test_no_known_code_identifies_nobody(title):
    assert titles.resolve(title, CODES) == (None, 'none')


def test_two_different_codes_are_ambiguous_and_never_guessed():
    assert titles.resolve('A1 y M2 en vivo', CODES) == (None, 'ambiguous')
    assert titles.note_for('A1 y M2', CODES, None) == 'titulo_con_varios_codigos'
    assert titles.note_for('Sin código', CODES, None) == 'titulo_sin_codigo'
    assert titles.note_for(None, CODES, None) == 'sin_titulo'
    assert titles.note_for('A1', CODES, 'TK-A01') is None


def test_the_roster_matches_the_agreed_codes():
    assert {r['code']: (r['name'], r['id']) for r in ROSTER} == {
        'A1': ('Ash', 'TK-A01'), 'M2': ('Mari', 'TK-M02'), 'L3': ('Lu', 'TK-L03'),
        'B4': ('Bri', 'TK-B04'), 'F5': ('Fer', 'TK-F05'), 'N6': ('Nahit', 'TK-N06')}


def test_room_info_title_is_read_defensively():
    assert extract_title({'title': 'Live A1'}) == 'Live A1'
    assert extract_title({'room': {'title': 'Live M2'}}) == 'Live M2'
    assert extract_title({'title': '  '}) is None
    assert extract_title(None) is None and extract_title({'x': 1}) is None


# ---------- end to end ----------

@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': {'ana': 'agente_ventas', 'jefa': 'jefe_marketing'}.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)


async def seed(factory):
    async with factory() as s:
        connection = await s.connection()
        await connection.run_sync(seed_roster)
        await s.commit()


async def broadcast(factory, bid, title, account='medical', hours=1):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with factory() as s, s.begin():
        s.add(Broadcast(id=bid, account_id=account, tiktok_username=f'user.{account}',
                        room_id=f'r{bid}', started_at=now - timedelta(hours=hours),
                        end_confirmed=False, title=title))
        s.add(RawEvent(event_id=f'{account}:r{bid}:like:1', account_id=account, broadcast_id=bid,
                       type='like', occurred_at=now - timedelta(minutes=5), payload={'count': 3}))


async def live(client, live_id):
    return (await client.get(f'{MKT}/lives/{live_id}', headers=READ)).json()


async def test_title_code_names_the_responsible_of_the_live_and_its_metrics(env):
    client, factory = env
    await seed(factory)
    await broadcast(factory, 1, 'Cirugías en vivo L3')
    await broadcast(factory, 2, 'Rinoplastia B4', account='medical-2')
    await publish_batch(factory)
    one, two = await live(client, 'TT-1'), await live(client, 'TT-2')
    assert (one['tiktoker'], one['tiktoker_id'], one['title']) == ('Lu', 'TK-L03', 'Cirugías en vivo L3')
    assert one['responsible_source'] == 'title' and one['responsible_note'] is None
    assert two['tiktoker'] == 'Bri'
    # Metrics can be validated per TikToker.
    ranking = (await client.get(f'{MKT}/ranking', headers=READ)).json()['items']
    assert {r['tiktoker'] for r in ranking} == {'Lu', 'Bri'}
    only_lu = (await client.get(f'{MKT}/lives', headers=READ,
                                params={'tiktoker_id': 'TK-L03'})).json()['items']
    assert [i['id'] for i in only_lu] == ['TT-1']
    overview = (await client.get(f'{MKT}/overview', headers=READ,
                                 params={'tiktoker_id': 'TK-B04'})).json()
    assert overview['lives'] == 1 and overview['likes'] == 3
    monitor = (await client.get(f'{MKT}/monitor', headers=READ)).json()['accounts']
    assert {a['account_id']: a['tiktoker'] for a in monitor}['medical'] == 'Lu'


async def test_without_a_usable_code_the_live_stays_unassigned_with_the_reason(env):
    client, factory = env
    await seed(factory)
    await broadcast(factory, 1, 'Cirugías sin código')
    await broadcast(factory, 2, 'A1 con M2 juntas', account='medical-2')
    await broadcast(factory, 3, None, account='medical-3')
    await publish_batch(factory)
    cases = {i: await live(client, f'TT-{i}') for i in (1, 2, 3)}
    assert [(c['tiktoker'], c['responsible_note']) for c in cases.values()] == [
        ('Sin asignar', 'titulo_sin_codigo'), ('Sin asignar', 'titulo_con_varios_codigos'),
        ('Sin asignar', 'sin_titulo')]
    assert all(c['responsible_source'] is None for c in cases.values())


async def test_an_edited_title_is_followed_but_never_loses_the_known_host(env):
    client, factory = env
    await seed(factory)
    await broadcast(factory, 1, 'Live M2')
    await publish_batch(factory)
    assert (await live(client, 'TT-1'))['tiktoker'] == 'Mari'
    async with factory() as s, s.begin():
        (await s.get(Broadcast, 1)).title = 'Live F5'     # the host changes the title
    await publish_batch(factory)
    assert (await live(client, 'TT-1'))['tiktoker'] == 'Fer'
    async with factory() as s, s.begin():
        (await s.get(Broadcast, 1)).title = 'Live sin código'
    await publish_batch(factory)
    detail = await live(client, 'TT-1')
    assert detail['tiktoker'] == 'Fer' and detail['title'] == 'Live sin código'


async def test_a_manual_assignment_wins_over_the_title_until_it_is_cleared(env):
    client, factory = env
    await seed(factory)
    await broadcast(factory, 1, 'Live A1')
    await publish_batch(factory)
    assert (await live(client, 'TT-1'))['tiktoker'] == 'Ash'
    fixed = await client.patch(f'{API}/lives/TT-1', headers=INGEST,
                               json={'tiktoker_id': 'TK-N06'})
    assert fixed.status_code == 200 and fixed.json()['tiktoker'] == 'Nahit'
    assert fixed.json()['responsible_source'] == 'manual'
    async with factory() as s, s.begin():
        (await s.get(Broadcast, 1)).title = 'Live L3'
    await publish_batch(factory)
    assert (await live(client, 'TT-1'))['tiktoker'] == 'Nahit'     # the title is only recorded
    back = await client.patch(f'{API}/lives/TT-1', headers=INGEST, json={'tiktoker_id': None})
    assert back.json()['tiktoker'] == 'Lu' and back.json()['responsible_source'] == 'title'
    assert (await client.patch(f'{API}/lives/TT-1', headers=INGEST,
                               json={'tiktoker_id': 'nadie'})).status_code == 422
    assert (await client.patch(f'{API}/lives/TT-1', headers=READ,
                               json={'title': 'x'})).status_code == 403


async def test_lives_created_through_the_api_read_their_title_too(env):
    client, factory = env
    await seed(factory)
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'm', 'username': 'medical.cirugias'})
    made = await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'API-1', 'account_id': 'medical', 'title': 'Consulta N6 en vivo'})
    assert made.status_code == 201
    assert (await live(client, 'API-1'))['tiktoker'] == 'Nahit'
    explicit = await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'API-2', 'account_id': 'medical', 'tiktoker_id': 'TK-A01',
        'title': 'Consulta N6'})
    assert explicit.status_code == 201
    assert (await live(client, 'API-2'))['tiktoker'] == 'Ash'    # explicit beats the title


async def test_contacts_show_the_responsible_named_in_the_title(env, people):
    client, factory = env
    await seed(factory)
    await broadcast(factory, 1, 'Rinoplastia L3')
    await broadcast(factory, 2, 'Sin código', account='medical-2')
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with factory() as s, s.begin():
        s.add(UserRole(user_id='ana', role='agente_ventas', display_name='Ana'))
        for bid, account, phone in ((1, 'medical', 'Mi número es 987654321'),
                                    (2, 'medical-2', 'Escríbeme al 976543210')):
            s.add(RawEvent(event_id=f'{account}:r{bid}:comment:1', account_id=account,
                           broadcast_id=bid, type='comment', occurred_at=now - timedelta(minutes=2),
                           payload={'user': '9', 'username': 'maria'}, raw_text=phone))
    await publish_batch(factory)
    items = (await client.get('/api/inbox', headers={'Authorization': 'Bearer user:ana'},
                              params={'phone_only': True})).json()['items']
    assert {i['phone']: i['liveHost'] for i in items} == {
        '+51987654321': 'Lu', '+51976543210': 'Sin asignar'}


async def test_roster_seed_is_idempotent_and_codes_are_unique(env):
    client, factory = env
    await seed(factory)
    await seed(factory)
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(m.Tiktoker)) == 6
        lu = await s.get(m.Tiktoker, 'TK-L03')
        assert (lu.name, lu.full_name, lu.code) == ('Lu', 'Lucía', 'L3')
    taken = await client.post(f'{API}/tiktokers', headers=INGEST, json={
        'id': 'TK-X99', 'name': 'Otra', 'code': 'l3'})
    assert taken.status_code == 409
    ok = await client.post(f'{API}/tiktokers', headers=INGEST, json={
        'id': 'TK-X99', 'name': 'Otra', 'code': 'x9'})
    assert ok.status_code == 200 and ok.json()['code'] == 'X9'
    assert (await client.post(f'{API}/tiktokers', headers=INGEST, json={
        'id': 'TK-Y1', 'name': 'Mala', 'code': 'ABC'})).status_code == 422
