"""Alerts for contacts that re-send their number after being contacted, reminders for agents,
"no me contactan" comments and the contact download."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import select, update

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.social_live import models as m
from livepulse.shared import auth as clerk

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, MKT = '/api/social-live', '/api/marketing/tiktok'
ROLES = {'ana': 'agente_ventas', 'bea': 'agente_ventas', 'sup': 'supervisor',
         'jefa': 'jefe_marketing', 'gus': 'gerente'}


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': ROLES.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


async def comment(client, live_id, username, text, minutes_ago, event_id=None):
    r = await client.post(f'{API}/lives/{live_id}/comments', headers=INGEST, json={
        'username': username, 'text': text, 'timestamp': ago(minutes_ago),
        **({'event_id': event_id} if event_id else {})})
    assert r.status_code == 200, r.text


@pytest.fixture
async def world(env, people):
    """Two accounts, a morning and an afternoon live on the first one, one on the second."""
    client, factory = env
    for account, username in (('medical', 'medical.cirugias'), ('medical-2', 'medical.cirugias2')):
        await client.post(f'{API}/accounts', headers=INGEST,
                          json={'id': account, 'name': account, 'username': username})
    for live_id, account, started in (('AM', 'medical', 600), ('PM', 'medical', 300),
                                      ('OTRA', 'medical-2', 300)):
        r = await client.post(f'{API}/lives', headers=INGEST, json={
            'live_id': live_id, 'account_id': account, 'started_at': ago(started)})
        assert r.status_code == 201
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id=u, role=r, display_name=u.title()) for u, r in ROLES.items()])
    return client, factory


async def contact_id(factory, phone='+51987654321'):
    async with factory() as s:
        return await s.scalar(select(m.PhoneRegistry.id).where(m.PhoneRegistry.phone == phone))


async def mark_contacted(factory, phone, minutes_ago, advisor='ana'):
    """Set the moment the agent marked it, exactly (the API would stamp 'now')."""
    async with factory() as s, s.begin():
        await s.execute(update(m.PhoneRegistry).where(m.PhoneRegistry.phone == phone).values(
            status='contacted', advisor_id=advisor, assigned_at=NOW - timedelta(minutes=minutes_ago + 5),
            contacted_at=NOW - timedelta(minutes=minutes_ago)))


async def alerts(client, who='jefa', status='open'):
    return (await client.get('/api/alerts', headers=person(who), params={'status': status})).json()


async def test_a_contact_still_new_that_insists_raises_no_alert(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 120)
    await comment(client, 'AM', 'pepito', 'por favor escríbanme al 987654321', 100)
    await comment(client, 'PM', 'pepito', 'sigo aquí 987654321', 30)
    assert (await alerts(client))['total'] == 0


async def test_same_live_after_the_marking_alerts_only_after_the_waiting_time(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 120)
    await mark_contacted(factory, '+51987654321', 90)           # marked 90 min ago
    await comment(client, 'AM', 'pepito', 'otra vez 987654321', 85)   # 5 min after: in flight
    await comment(client, 'AM', 'pepito', 'llámenme 987654321', 100)   # BEFORE it was marked
    assert (await alerts(client))['total'] == 0
    await comment(client, 'AM', 'pepito', 'sigo esperando 987654321', 70)   # 20 min after
    result = await alerts(client)
    assert result['total'] == 1
    item = result['items'][0]
    assert item['kind'] == 'same_live' and item['phone'] == '+51987654321'
    assert item['advisor'] == 'Ana' and item['minutes_after_contact'] == 20
    assert item['tiktok_username'] == 'pepito' and item['status'] == 'open'
    # Writing again in that live reinforces the same alert instead of opening more.
    await comment(client, 'AM', 'pepito', 'hola? 987654321', 60)
    result = await alerts(client)
    assert result['total'] == 1 and result['items'][0]['repeats'] == 2


async def test_another_live_or_another_account_after_the_marking_alerts_at_once(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 200)
    await mark_contacted(factory, '+51987654321', 150)
    await comment(client, 'PM', 'pepito', 'de nuevo 987654321', 149)        # 1 min after marking
    await comment(client, 'OTRA', 'pepito', 'también aquí 987654321', 100)
    kinds = {i['live_id']: i['kind'] for i in (await alerts(client))['items']}
    assert kinds == {'PM': 'other_live', 'OTRA': 'other_account'}
    # Reappearing in another live BEFORE being marked is not an alert.
    await comment(client, 'AM', 'luis', 'mi número es 976543210', 220)
    await comment(client, 'PM', 'luis', 'sigo 976543210', 180)
    await mark_contacted(factory, '+51976543210', 10)
    assert (await alerts(client))['total'] == 2


async def test_only_supervisor_marketing_head_and_manager_see_and_review_alerts(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 200)
    await mark_contacted(factory, '+51987654321', 150)
    await comment(client, 'PM', 'pepito', 'de nuevo 987654321', 100)
    for who in ('jefa', 'gus', 'sup'):
        assert (await client.get('/api/alerts', headers=person(who))).status_code == 200, who
    for denied in (person('ana'), INGEST, READ):
        assert (await client.get('/api/alerts', headers=denied)).status_code == 403
        assert (await client.get('/api/complaints', headers=denied)).status_code == 403
    alert_id = (await alerts(client))['items'][0]['id']
    assert (await client.patch(f'/api/alerts/{alert_id}', headers=person('ana'),
                               json={'status': 'reviewed'})).status_code == 403
    done = await client.patch(f'/api/alerts/{alert_id}', headers=person('gus'), json={
        'status': 'reviewed', 'note': 'Se pidió captura del chat; sí lo contactaron.'})
    assert done.status_code == 200
    assert done.json()['status'] == 'reviewed' and done.json()['reviewed_by'] == 'Gus'
    assert (await alerts(client))['total'] == 0
    assert (await alerts(client, status='reviewed'))['items'][0]['note'].startswith('Se pidió')
    # A later repeat is counted but never reopens a reviewed alert.
    await comment(client, 'PM', 'pepito', 'otra vez 987654321', 50)
    assert (await alerts(client))['total'] == 0
    assert (await alerts(client, status='reviewed'))['items'][0]['repeats'] == 2


async def test_the_bell_gives_each_role_only_its_own_notifications(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 200)
    await comment(client, 'AM', 'rosa', 'mi número es 976543210', 200)
    await comment(client, 'AM', 'tere', 'mi número es 965432109', 200)
    await mark_contacted(factory, '+51987654321', 150)
    await comment(client, 'PM', 'pepito', 'de nuevo 987654321', 100)
    # ana holds two pending chats: one for 15 min, one for 25 min; tere's is unclaimed.
    async with factory() as s, s.begin():
        for phone, minutes in (('+51976543210', 15), ('+51965432109', 25)):
            await s.execute(update(m.PhoneRegistry).where(m.PhoneRegistry.phone == phone).values(
                advisor_id='ana', assigned_at=NOW - timedelta(minutes=minutes)))
    agent = (await client.get('/api/notifications', headers=person('ana'))).json()
    assert agent['alerts'] is None                       # agents never see alerts
    reminders = agent['agent']
    assert (reminders['mine_pending'], reminders['mine_over_first'],
            reminders['mine_over_second']) == (2, 2, 1)
    assert reminders['first_minutes'] == 10 and reminders['second_minutes'] == 20
    assert agent['count'] == 2
    for who in ('jefa', 'gus'):
        manager = (await client.get('/api/notifications', headers=person(who))).json()
        assert manager['agent'] is None and manager['alerts'] == {'open': 1, 'complaints_open': 0}
        assert manager['count'] == 1
    both = (await client.get('/api/notifications', headers=person('sup'))).json()
    assert both['alerts']['open'] == 1 and both['agent'] is not None
    assert (await client.get('/api/notifications', headers=READ)).status_code == 403


async def test_unclaimed_chats_waiting_remind_the_agents_but_young_ones_do_not(world):
    client, factory = world
    await comment(client, 'AM', 'rosa', 'mi número es 976543210', 40)
    await comment(client, 'PM', 'tere', 'mi número es 965432109', 3)
    reminders = (await client.get('/api/notifications', headers=person('bea'))).json()['agent']
    assert reminders['unclaimed_waiting'] == 1 and reminders['mine_pending'] == 0


async def test_comments_saying_nobody_contacted_them_show_who_the_user_is(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 200)
    await mark_contacted(factory, '+51987654321', 150)
    await comment(client, 'PM', 'pepito', 'les escribo y no me contestan, nadie me llamó', 20)
    await comment(client, 'PM', 'otro', 'qué bonito el live', 19)
    await comment(client, 'PM', 'sin_numero', 'sigo esperando que me contacten', 18)
    result = (await client.get('/api/complaints', headers=person('jefa'))).json()
    by_user = {i['username']: i for i in result['items']}
    assert set(by_user) == {'pepito', 'sin_numero'} and result['total'] == 2
    pepito = by_user['pepito']
    assert pepito['contacts'][0]['phone'] == '+51987654321'
    assert pepito['contacts'][0]['status'] == 'contacted' and pepito['contacts'][0]['advisor'] == 'Ana'
    assert by_user['sin_numero']['contacts'] == []      # no number on record for that user
    bell = (await client.get('/api/notifications', headers=person('gus'))).json()
    assert bell['alerts']['complaints_open'] == 2
    assert (await client.patch(f"/api/complaints/{pepito['id']}", headers=person('ana'),
                               json={'reviewed': True})).status_code == 403
    ok = await client.patch(f"/api/complaints/{pepito['id']}", headers=person('sup'),
                            json={'reviewed': True})
    assert ok.status_code == 200
    assert (await client.get('/api/complaints', headers=person('jefa'))).json()['total'] == 1
    reviewed = (await client.get('/api/complaints', headers=person('jefa'),
                                 params={'status': 'reviewed'})).json()['items']
    assert reviewed[0]['reviewed_by'] == 'Sup'


async def test_the_contact_list_download_is_for_marketing_roles_and_is_audited(world):
    client, factory = world
    await comment(client, 'AM', 'pepito', 'mi número es 987654321', 200)
    await comment(client, 'AM', 'rosa', 'mi número es 976543210', 190)
    await comment(client, 'PM', 'pepito', 'de nuevo 987654321', 100)      # a reappearance
    await mark_contacted(factory, '+51987654321', 150)
    await comment(client, 'OTRA', 'pepito', 'aquí también 987654321', 50)  # opens an alert
    url = f'{MKT}/contacts/export'
    for denied in (person('ana'), READ, INGEST, {}):
        assert (await client.get(url, headers=denied)).status_code in (401, 403)
    res = await client.get(url, headers=person('jefa'))
    assert res.status_code == 200 and 'spreadsheetml' in res.headers['content-type']
    sheet = load_workbook(io.BytesIO(res.content)).active
    rows = list(sheet.values)
    assert rows[0][:3] == ('teléfono', 'estado', 'asesor') and len(rows) == 3
    by_phone = {r[0]: r for r in rows[1:]}
    pepito = by_phone['+51987654321']
    assert pepito[1] == 'Contactado' and pepito[2] == 'Ana'
    assert int(pepito[11]) == 3 and int(pepito[12]) == 1       # 3 appearances, 1 open alert
    assert int(by_phone['+51976543210'][11]) == 1
    only_new = load_workbook(io.BytesIO((await client.get(
        url, headers=person('sup'), params={'status': 'new'})).content)).active
    assert len(list(only_new.values)) == 2
    async with factory() as s:
        audit = (await s.scalars(select(m.ExportAudit))).all()
    assert [(a.actor, a.kind, a.rows) for a in audit] == [('jefa', 'contacts', 2), ('sup', 'contacts', 1)]
