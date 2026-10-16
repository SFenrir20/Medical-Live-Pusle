"""Review findings: global phone dedupe, explicit LIVE responsibility, retention, agent work queue,
and the bridge from the TikTok monitor to the Social Live model."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.social_live import models as m
from livepulse.modules.social_live.publisher import publish_batch
from livepulse.modules.social_live.retention import purge_expired
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, MKT = '/api/social-live', '/api/marketing/tiktok'


# What Clerk's Public metadata would say for each test person (boss = ADMIN_USER_IDS).
CLERK_ROLES = {'ana': 'agente_ventas', 'bea': 'agente_ventas', 'sup': 'supervisor',
               'mk': 'jefe_marketing', 'jefa': 'jefe_marketing'}


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(settings, 'admin_user_ids', ['boss'])
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': CLERK_ROLES.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)


async def setup_account(client, account='medical', username='medical.cirugias'):
    r = await client.post(f'{API}/accounts', headers=INGEST,
                          json={'id': account, 'name': account, 'username': username})
    assert r.status_code == 200, r.text


async def new_live(client, live_id, account='medical', started=None, tiktoker=None):
    body = {'live_id': live_id, 'account_id': account,
            'started_at': (started or datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()}
    if tiktoker:
        body['tiktoker_id'] = tiktoker
    r = await client.post(f'{API}/lives', headers=INGEST, json=body)
    assert r.status_code == 201, r.text


async def add_phone(client, live_id, phone, at=None, user='u'):
    r = await client.post(f'{API}/lives/{live_id}/phones', headers=INGEST, json={
        'phone': phone, 'tiktok_username': user,
        'captured_at': (at or datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()})
    assert r.status_code in (200, 201), r.text
    return r.json()


async def test_a_number_is_new_once_across_lives(env):
    client, _ = env
    await setup_account(client)
    await new_live(client, 'LIVE-A', started=datetime.now(timezone.utc) - timedelta(hours=6))
    await new_live(client, 'LIVE-B')
    first = await add_phone(client, 'LIVE-A', '987654321',
                            datetime.now(timezone.utc) - timedelta(hours=5))
    again = await add_phone(client, 'LIVE-B', '+51 987 654 321')
    assert first['is_new'] is True and again['is_new'] is False and again['created'] is True
    await add_phone(client, 'LIVE-B', '976543210')

    overview = (await client.get(f'{MKT}/overview', headers=READ)).json()
    assert overview['phones'] == 2          # distinct numbers, not appearances
    assert overview['phone_mentions'] == 3  # every appearance is kept separately
    b = (await client.get(f'{MKT}/lives/LIVE-B/metrics', headers=READ)).json()
    assert b['phones_captured'] == 1 and b['phone_mentions'] == 2
    listing = (await client.get(f'{MKT}/lives/LIVE-B/phones', headers=READ)).json()['items']
    assert sorted(i['is_new'] for i in listing) == [False, True]
    assert (await client.get(f'{MKT}/contact-performance', headers=READ)).json()['phones'] == 2
    assert (await client.get(f'{MKT}/hourly-performance', headers=READ)).json()['total'] == 2


async def test_explicit_host_assignment_and_unassigned_lives(env):
    client, factory = env
    await setup_account(client)
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=4)
    async with factory() as s, s.begin():
        s.add(m.Tiktoker(id='ana', name='Ana Ruiz'))
    await new_live(client, 'LIVE-1', started=start, tiktoker='ana')
    await new_live(client, 'LIVE-2', started=start)
    await add_phone(client, 'LIVE-1', '987654321', start + timedelta(minutes=30))
    await add_phone(client, 'LIVE-1', '976543210', start + timedelta(minutes=90))
    await add_phone(client, 'LIVE-2', '965432109', start + timedelta(minutes=150))

    board = {i['tiktoker']: i for i in
             (await client.get(f'{MKT}/ranking', headers=READ)).json()['items']}
    assert board['Ana Ruiz']['phones'] == 2 and board['Ana Ruiz']['rank'] == 1
    assert board['Sin asignar']['phones'] == 1 and board['Sin asignar']['rank'] is None
    detail = (await client.get(f'{MKT}/lives/LIVE-1', headers=READ)).json()
    assert [i['tiktoker'] for i in detail['intervals']] == ['Ana Ruiz']
    assert detail['tiktokers'][0]['share'] == 1.0
    only_ana = (await client.get(f'{MKT}/contact-performance', headers=READ,
                                 params={'tiktoker_id': 'ana'})).json()
    assert only_ana['phones'] == 2
    only_lives = (await client.get(f'{MKT}/lives', headers=READ,
                                   params={'tiktoker_id': 'ana'})).json()['items']
    assert [row['id'] for row in only_lives] == ['LIVE-1']
    assert (await client.get(f'{MKT}/lives', headers=READ,
                             params={'tiktoker_id': 'nadie'})).json()['items'] == []


async def test_retention_keeps_deduplication_of_open_lives(env):
    client, factory = env
    await setup_account(client)
    await new_live(client, 'LIVE-OPEN')
    event = {'event_type': 'like', 'value': 7, 'event_id': 'likes-1'}
    first = (await client.post(f'{API}/lives/LIVE-OPEN/events', headers=INGEST,
                               json=event)).json()
    assert first['accepted'] == 1
    old = datetime.now(timezone.utc) - timedelta(days=45)
    async with factory() as s, s.begin():
        await s.execute(update(m.LiveEventKey).values(created_at=old))
    await purge_expired(factory)
    retry = (await client.post(f'{API}/lives/LIVE-OPEN/events', headers=INGEST,
                               json=event)).json()
    assert retry['accepted'] == 0 and retry['duplicates'] == 1
    metrics = (await client.get(f'{MKT}/lives/LIVE-OPEN/metrics', headers=READ)).json()
    assert metrics['likes_count'] == 7  # not 14

    # A finished live no longer accepts events, so its keys can safely go.
    async with factory() as s, s.begin():
        await s.execute(update(m.Live).values(
            status='finished', ended_at=old, started_at=old - timedelta(hours=1),
            duration_seconds=3600))
    removed = await purge_expired(factory)
    assert removed['event_keys'] == 1
    late = await client.post(f'{API}/lives/LIVE-OPEN/events', headers=INGEST, json=event)
    assert late.status_code == 409
    metrics = (await client.get(f'{MKT}/lives/LIVE-OPEN/metrics', headers=READ)).json()
    assert metrics['likes_count'] == 7


async def test_sales_agent_works_leads_through_the_api(env, people):
    client, factory = env
    await setup_account(client)
    await new_live(client, 'LIVE-1')
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id='ana', role='agente_ventas', display_name='Ana Ruiz'),
                   UserRole(user_id='bea', role='agente_ventas', display_name='Bea Lira'),
                   UserRole(user_id='sup', role='supervisor', display_name='Sara Sup'),
                   UserRole(user_id='mk', role='gerente', display_name='Gerente')])
    await client.post(f'{API}/lives/LIVE-1/comments', headers=INGEST, json={
        'username': 'maria', 'text': 'quiero información, mi número es 987654321'})
    await client.post(f'{API}/lives/LIVE-1/comments', headers=INGEST,
                      json={'username': 'luis', 'text': 'qué bonito'})

    # The capture token never reaches the work queue; people with the role do.
    assert (await client.get('/api/inbox', headers=INGEST)).status_code == 403
    assert (await client.get('/api/inbox', headers=person('mk'))).status_code == 403
    inbox = (await client.get('/api/inbox', headers=person('ana'))).json()
    kinds = sorted(i['kind'] for i in inbox['items'])
    assert kinds == ['comment', 'lead']
    lead = next(i for i in inbox['items'] if i['kind'] == 'lead')
    assert lead['phone'] == '+51987654321' and lead['user'] == '@maria'
    assert lead['message'].startswith('quiero información') and lead['owner'] is None
    only_phones = (await client.get('/api/inbox', headers=person('ana'),
                                    params={'phone_only': True})).json()['items']
    assert [i['kind'] for i in only_phones] == ['lead']

    # Claim -> contacted persists (a new request sees it) and sets contacted_at once.
    claimed = await client.patch(f"/api/leads/{lead['id']}", headers=person('ana'),
                                 json={'action': 'claim', 'expect_unassigned': True})
    assert claimed.status_code == 200 and claimed.json()['owner'] == 'Ana Ruiz'
    assert claimed.json()['isMine'] is True
    other = await client.patch(f"/api/leads/{lead['id']}", headers=person('bea'),
                               json={'action': 'claim', 'expect_unassigned': True})
    assert other.status_code == 409
    forbidden = await client.patch(f"/api/leads/{lead['id']}", headers=person('bea'),
                                   json={'status': 'contacted'})
    assert forbidden.status_code == 404  # another advisor's contact is not even visible
    stale = await client.patch(f"/api/leads/{lead['id']}", headers=person('ana'),
                               json={'status': 'contacted', 'expected_status': 'qualified'})
    assert stale.status_code == 409
    done = await client.patch(f"/api/leads/{lead['id']}", headers=person('ana'),
                              json={'status': 'contacted', 'expected_status': 'new'})
    assert done.status_code == 200 and done.json()['status'] == 'Contactado'
    assert done.json()['contactedAt'] is not None
    mine = (await client.get('/api/inbox', headers=person('ana'),
                             params={'scope': 'mine'})).json()['items']
    assert [(i['owner'], i['status']) for i in mine] == [('Ana Ruiz', 'Contactado')]
    assert (await client.get('/api/inbox', headers=person('bea'),
                             params={'scope': 'mine'})).json()['items'] == []

    # Only a supervisor assigns to someone else.
    assert (await client.patch(f"/api/leads/{lead['id']}", headers=person('ana'),
                               json={'advisor_id': 'bea'})).status_code == 403
    assigned = await client.patch(f"/api/leads/{lead['id']}", headers=person('sup'),
                                  json={'advisor_id': 'bea'})
    assert assigned.status_code == 200 and assigned.json()['owner'] == 'Bea Lira'

    # Marketing sees counts and the team, never the leads themselves.
    summary = (await client.get('/api/leads/summary', headers=person('mk'))).json()
    assert summary['unassigned'] == 0
    by_name = {a['name']: a for a in summary['agents']}
    assert by_name['Bea Lira']['assigned'] == 1 and by_name['Bea Lira']['contacted'] == 1
    assert 'Ana Ruiz' in by_name
    assert (await client.get('/api/team', headers=person('mk'))).status_code == 200


async def test_monitor_events_reach_the_new_reports(env):
    client, factory = env
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with factory() as s, s.begin():
        s.add(Broadcast(id=7, account_id='medical', tiktok_username='medical.cirugias',
                        room_id='r7', started_at=now - timedelta(hours=1), end_confirmed=False))
        base = now - timedelta(minutes=30)
        for i, (kind, payload, text) in enumerate([
                ('comment', {'user': '77', 'username': 'maria', 'nickname': 'Maria'},
                 'me interesa el precio, 985//857#968'),
                ('comment', {'user': '78', 'username': 'luis'}, 'qué bonito'),
                ('like', {'user': '77', 'count': 12}, None),
                ('share', {'user': '78'}, None), ('join', {'user': '79'}, None),
                ('follow', {'user': '79'}, None),
                ('audience', {'viewers': 41}, None), ('audience', {'viewers': 33}, None),
                ('gift', {'user': '77', 'gift_type': 1, 'repeat_end': 0, 'repeat_count': 2,
                          'diamond_count': 5}, None),
                ('gift', {'user': '77', 'gift_type': 1, 'repeat_end': 1, 'repeat_count': 3,
                          'diamond_count': 5}, None)]):
            s.add(RawEvent(event_id=f'medical:r7:{kind}:{i}', account_id='medical',
                           broadcast_id=7, type=kind, occurred_at=base + timedelta(minutes=i),
                           payload=payload, raw_text=text))
    assert await publish_batch(factory) == 10
    assert await publish_batch(factory) == 0  # idempotent: nothing is counted twice

    metrics = (await client.get(f'{MKT}/lives/TT-7/metrics', headers=READ)).json()
    assert metrics['comments_count'] == 2 and metrics['likes_count'] == 12
    assert metrics['shares_count'] == 1 and metrics['views'] == 1
    assert metrics['new_followers'] == 1 and metrics['peak_viewers'] == 41
    assert metrics['average_viewers'] == 37.0 and metrics['unique_viewers'] is None
    assert metrics['donations_count'] == 3  # only the final tick of the streak
    assert metrics['interested_viewers'] == 1 and metrics['phones_captured'] == 1
    phones = (await client.get(f'{MKT}/lives/TT-7/phones', headers=READ)).json()['items']
    assert phones[0]['phone'] == '+51985857968' and phones[0]['tiktok_username'] == 'maria'
    detail = (await client.get(f'{MKT}/lives/TT-7', headers=READ)).json()
    assert detail['status'] == 'live' and detail['account'] == '@medical.cirugias'

    # The monitor confirms the end -> the live closes with the real end time.
    async with factory() as s, s.begin():
        broadcast = await s.get(Broadcast, 7)
        broadcast.ended_at, broadcast.end_confirmed = now, True
    await publish_batch(factory)
    done = (await client.get(f'{MKT}/lives/TT-7', headers=READ)).json()
    assert done['status'] == 'finished' and done['duration_seconds'] == 3600
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(m.LiveComment)) == 2
