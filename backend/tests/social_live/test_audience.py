"""Ranking of fans: who comments, likes, gives gifts or stays around the most. Only for the
managers; never shows phones."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.social_live import models as m
from livepulse.modules.social_live.audience import backfill_from_raw_events
from livepulse.modules.social_live.publisher import publish_batch
from livepulse.modules.social_live.retention import purge_expired
from livepulse.modules.social_live.service import aware_utc
from livepulse.shared import auth as clerk

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, TOP = '/api/social-live', '/api/audience/top'
ROLES = {'ana': 'agente_ventas', 'sup': 'supervisor', 'jefa': 'jefe_marketing', 'gus': 'gerente'}
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': ROLES.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)


@pytest.fixture
async def world(env, people):
    client, factory = env
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'medical', 'username': 'medical.cirugias'})
    for live_id, started in (('AM', 600), ('PM', 300)):
        r = await client.post(f'{API}/lives', headers=INGEST, json={
            'live_id': live_id, 'account_id': 'medical', 'started_at': ago(started)})
        assert r.status_code == 201
    return client, factory


async def send(client, live_id, *events):
    r = await client.post(f'{API}/lives/{live_id}/events', headers=INGEST,
                          json={'events': list(events)})
    assert r.status_code == 200, r.text


def ev(kind, user, minutes_ago, **extra):
    return {'event_type': kind, 'username': user, 'timestamp': ago(minutes_ago), **extra}


async def test_counters_per_user_and_ranking(world):
    client, _ = world
    await send(client, 'AM',
               ev('comment', 'Rachel', 50, text='hola', display_name='Rachel 🌻'),
               ev('comment', '@rachel', 40, text='quiero info'),
               ev('like', 'rachel', 35, value=12),
               ev('donation', 'rachel', 30, value=3, diamonds=15),
               ev('comment', 'felix', 45, text='buenas'),
               ev('share', 'felix', 20), ev('follow', 'felix', 10),
               ev('view', 'luis', 55))
    body = (await client.get(TOP, params={'live_id': 'AM'}, headers=person('jefa'))).json()
    assert body['scope'] == 'live' and body['members'] == 3
    first, second, third = body['items']
    # '@rachel' and 'Rachel' are the same person
    assert (first['user_key'], first['comments'], first['likes']) == ('rachel', 2, 12)
    assert (first['gifts'], first['diamonds']) == (3, 15)
    assert first['name'] == 'Rachel 🌻'
    # felix has no gifts; ties on diamonds fall back to comments, then likes
    assert second['user_key'] == 'felix' and second['shares'] == 1 and second['followed'] is True
    assert third['user_key'] == 'luis' and third['comments'] == 0
    # presence = first to last time seen (estimate): rachel 50 -> 30 minutes ago
    assert first['presence_seconds'] == 20 * 60
    assert 'phone' not in first and first['left_contact'] is False

    by_presence = (await client.get(TOP, params={'live_id': 'AM', 'sort': 'presence'},
                                    headers=person('sup'))).json()
    # felix: 45 -> 10 minutes ago (35 min) stayed visible longer than rachel (20 min)
    assert by_presence['items'][0]['user_key'] == 'felix'
    assert by_presence['items'][0]['presence_seconds'] == 35 * 60


async def test_same_event_is_counted_once(world):
    client, _ = world
    event = ev('comment', 'felix', 10, text='hola', event_id='e-1')
    await send(client, 'AM', event)
    await send(client, 'AM', event)
    items = (await client.get(TOP, params={'live_id': 'AM'}, headers=person('gus'))).json()['items']
    assert items[0]['comments'] == 1


async def test_only_managers_see_it(world):
    client, _ = world
    assert (await client.get(TOP, headers=person('ana'))).status_code == 403
    assert (await client.get(TOP, headers=READ)).status_code == 403   # Medical 360 token
    assert (await client.get(TOP, headers=INGEST)).status_code == 403
    assert (await client.get(TOP)).status_code == 401
    for who in ('sup', 'jefa', 'gus'):
        assert (await client.get(TOP, headers=person(who))).status_code == 200
    assert (await client.get(TOP, params={'live_id': 'NOPE'},
                             headers=person('jefa'))).status_code == 404


async def test_recurring_fans_and_contact_flag_without_phone(world):
    client, _ = world
    await send(client, 'AM', ev('comment', 'felix', 400, text='hola'),
               ev('comment', 'luis', 390, text='hola'))
    await send(client, 'PM', ev('comment', 'Felix', 200, text='de nuevo'),
               ev('donation', 'felix', 190, value=1, diamonds=30))
    r = await client.post(f'{API}/lives/AM/phones', headers=INGEST, json={
        'phone': '987654321', 'tiktok_username': '@felix', 'source': 'comment'})
    assert r.status_code == 201
    body = (await client.get(TOP, params={'sort': 'lives', 'days': 7},
                             headers=person('jefa'))).json()
    assert body['scope'] == 'period' and body['members'] == 2
    felix = body['items'][0]
    assert (felix['user_key'], felix['lives'], felix['comments'], felix['diamonds']) == (
        'felix', 2, 2, 30)
    assert felix['left_contact'] is True and body['items'][1]['left_contact'] is False
    assert '987654321' not in str(body)


async def test_monitor_payload_feeds_the_ranking_and_backfill_matches(world):
    """The publisher (live ingestion) and the migration backfill must agree."""
    client, factory = world
    async with factory() as s, s.begin():
        s.add(Broadcast(id=9, account_id='medical', tiktok_username='medical.cirugias',
                        room_id='r9', started_at=NOW - timedelta(hours=1), end_confirmed=False))
        base = NOW - timedelta(minutes=30)
        for i, (kind, payload, text) in enumerate([
                ('comment', {'user': '77', 'username': 'maria', 'nickname': 'Maria'}, 'hola'),
                ('like', {'user': '77', 'username': 'maria', 'count': 12}, None),
                ('join', {'user': '77', 'username': 'maria'}, None),
                ('share', {'user': '78', 'username': 'luis'}, None),
                ('follow', {'user': '78', 'username': 'luis'}, None),
                ('audience', {'viewers': 41}, None),
                # a gift streak: only the final tick counts (3 x 5 diamonds)
                ('gift', {'user': '77', 'username': 'maria', 'gift_type': 1, 'repeat_end': 0,
                          'repeat_count': 2, 'diamond_count': 5}, None),
                ('gift', {'user': '77', 'username': 'maria', 'gift_type': 1, 'repeat_end': 1,
                          'repeat_count': 3, 'diamond_count': 5}, None),
                ('comment', {'user': '79'}, 'sin nombre de usuario')]):
            s.add(RawEvent(event_id=f'medical:r9:{kind}:{i}', account_id='medical',
                           broadcast_id=9, type=kind, occurred_at=base + timedelta(minutes=i),
                           payload=payload, raw_text=text))
    await publish_batch(factory)

    body = (await client.get(TOP, params={'live_id': 'TT-9'}, headers=person('sup'))).json()
    by_user = {i['user_key']: i for i in body['items']}
    maria = by_user['maria']
    assert (maria['comments'], maria['likes'], maria['gifts'], maria['diamonds']) == (1, 12, 3, 15)
    assert maria['name'] == 'Maria'
    assert by_user['luis']['follows'] == 1 and by_user['luis']['shares'] == 1
    assert '79' in by_user   # last resort name: the numeric id

    async with factory() as s:
        live_rows = {(r.user_key): (r.comments, r.likes, r.shares, r.gifts, r.diamonds,
                                    r.follows, r.joins, aware_utc(r.first_seen_at), aware_utc(r.last_seen_at))
                     for r in (await s.scalars(select(m.AudienceMember))).all()}
    async with factory() as s, s.begin():
        connection = await s.connection()
        written = await connection.run_sync(backfill_from_raw_events)
    assert written == len(live_rows)
    async with factory() as s:
        rebuilt = {(r.user_key): (r.comments, r.likes, r.shares, r.gifts, r.diamonds,
                                  r.follows, r.joins, aware_utc(r.first_seen_at), aware_utc(r.last_seen_at))
                   for r in (await s.scalars(select(m.AudienceMember))).all()}
    assert rebuilt == live_rows


async def test_purge_drops_old_counters(world):
    client, factory = world
    await send(client, 'AM', ev('comment', 'felix', 10, text='hola'))
    async with factory() as s, s.begin():
        s.add(m.AudienceMember(live_id='AM', user_key='viejo', username='viejo',
                               first_seen_at=NOW - timedelta(days=45),
                               last_seen_at=NOW - timedelta(days=40), comments=3))
    removed = await purge_expired(factory)
    assert removed['audience'] == 1
    items = (await client.get(TOP, params={'live_id': 'AM'}, headers=person('sup'))).json()['items']
    assert [i['user_key'] for i in items] == ['felix']
