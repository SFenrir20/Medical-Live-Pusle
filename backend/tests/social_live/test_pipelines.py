"""Funnels (embudos): the built-in funnel mirrors the contact status, custom funnels hold their own
cards, who may move or edit, and the numbers come from the log of moves."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.crm import models as cm
from livepulse.modules.whatsapp import service as wa
from livepulse.shared import auth as clerk

INGEST = {'Authorization': 'Bearer ingest-secret'}
API, WA, CRM = '/api/social-live', '/api/whatsapp', '/api/crm'
ROLES = {'ana': 'agente_ventas', 'bea': 'agente_ventas', 'jefa': 'jefe_marketing',
         'sup': 'supervisor'}
LIVE_PHONE = '+51987654321'      # captured in a LIVE (it has a contact)
CHAT_PHONE = '+51900000001'      # only ever seen on WhatsApp
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def auth(user):
    return {'Authorization': f'Bearer {user}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def verify(token):
        if token not in ROLES:
            raise HTTPException(401)
        return {'id': token, 'role': ROLES[token]}

    monkeypatch.setattr(clerk, 'verify_token', verify)


@pytest.fixture
async def world(env, people):
    client, factory = env
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id=u, role=r, display_name=u.title()) for u, r in ROLES.items()])
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'm', 'username': 'medical.cirugias'})
    await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'L1', 'account_id': 'medical',
        'started_at': (NOW - timedelta(hours=2)).isoformat()})
    r = await client.post(f'{API}/lives/L1/comments', headers=INGEST, json={
        'username': 'camila.rr', 'text': 'me interesa el precio 987654321',
        'timestamp': (NOW - timedelta(minutes=30)).isoformat()})
    assert r.status_code == 200, r.text
    return client, factory


async def open_chat(client, phone, user='ana'):
    r = await client.post(f'{WA}/conversations', headers=auth(user), json={'phone': phone})
    assert r.status_code == 200, r.text
    return r.json()['id']


async def claim(client, conversation, user='ana'):
    r = await client.post(f'{WA}/conversations/{conversation}/claim', headers=auth(user))
    assert r.status_code == 200, r.text


async def hear(factory, phone, text):
    async with factory() as s, s.begin():
        await wa.ingest(s, {'id': str(uuid4()), 'type': 'message', 'phone': phone,
                            'external_id': str(uuid4()), 'from_me': False,
                            'at': (NOW - timedelta(minutes=5)).isoformat(), 'body': text})


PIPES = f'{CRM}/pipelines'


async def default_funnel(client, user='ana'):
    r = await client.get(PIPES, headers=auth(user))
    assert r.status_code == 200, r.text
    (first, *_) = r.json()['items']
    assert first['default'] is True and first['name'] == 'Contactos'
    board = (await client.get(f'{PIPES}/{first["id"]}/board', headers=auth(user))).json()
    return first['id'], board


def column(board, name):
    return next(c for c in board['stages'] if c['name'] == name)


async def make_funnel(client, template='whatsapp', name='Comercial', user='sup'):
    r = await client.post(PIPES, headers=auth(user), json={'name': name, 'template': template})
    assert r.status_code == 201, r.text
    return r.json()


async def test_the_built_in_funnel_mirrors_the_contact_status(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    pipe, board = await default_funnel(client)
    assert [c['name'] for c in board['stages']] == ['Nuevo', 'Contactado', 'Cita agendada', 'Descartado']
    assert column(board, 'Nuevo')['count'] == 1 and board['total'] == 1
    card = column(board, 'Nuevo')['cards'][0]
    assert card['id'] == chat and card['value_cents'] == 0

    contacted = column(board, 'Contactado')['id']
    r = await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('ana'),
                         json={'stage_id': contacted, 'value_cents': 150000})
    assert r.status_code == 200, r.text
    assert r.json()['stage_id'] == contacted and r.json()['value_cents'] == 150000
    board = (await client.get(f'{PIPES}/{pipe}/board', headers=auth('ana'))).json()
    assert column(board, 'Contactado')['count'] == 1 and column(board, 'Contactado')['value_cents'] == 150000
    assert column(board, 'Nuevo')['count'] == 0
    # the inbox sees the same single truth
    detail = (await client.get(f'{CRM}/conversations/{chat}', headers=auth('ana'))).json()
    assert detail['stage'] == 'contacted'
    # a change made from the inbox is a move in the same funnel
    await client.patch(f'{CRM}/conversations/{chat}', headers=auth('ana'), json={'stage': 'qualified'})
    board = (await client.get(f'{PIPES}/{pipe}/board', headers=auth('ana'))).json()
    assert column(board, 'Cita agendada')['count'] == 1


async def test_a_live_contact_moves_with_its_own_status(world):
    client, factory = world
    await hear(factory, LIVE_PHONE, 'Hola')
    chat = await open_chat(client, LIVE_PHONE)
    await claim(client, chat)
    pipe, board = await default_funnel(client)
    done = column(board, 'Cita agendada')['id']
    r = await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('ana'), json={'stage_id': done})
    assert r.status_code == 200, r.text
    async with factory() as s:
        from livepulse.modules.social_live.models import PhoneRegistry
        assert (await s.scalar(select(PhoneRegistry.status).where(PhoneRegistry.phone == LIVE_PHONE))) == 'qualified'


async def test_only_who_owns_the_conversation_may_move_it(world):
    client, _ = world
    chat = await open_chat(client, CHAT_PHONE)
    pipe, board = await default_funnel(client)
    target = column(board, 'Contactado')['id']
    free = await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('ana'), json={'stage_id': target})
    assert free.status_code == 409                       # a free one must be taken first
    await claim(client, chat)
    assert (await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('bea'),
                             json={'stage_id': target})).status_code in (403, 404)
    assert (await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('jefa'),
                             json={'stage_id': target})).status_code == 403   # reviewers only look
    assert (await client.put(f'{PIPES}/{pipe}/cards/{chat}', headers=auth('sup'),
                             json={'stage_id': target})).status_code == 200


async def test_agents_cannot_build_funnels_but_the_supervisor_can(world):
    client, _ = world
    assert (await client.post(PIPES, headers=auth('ana'), json={'name': 'X'})).status_code == 403
    assert (await client.post(PIPES, headers=auth('jefa'), json={'name': 'X'})).status_code == 403
    assert (await client.post(PIPES, headers=auth('sup'),
                              json={'name': 'X', 'template': 'nope'})).status_code == 422
    made = await make_funnel(client, 'tiktok_live', 'Comercial')
    assert [s['name'] for s in made['stages']][:2] == ['Contactos captados', 'Primer contacto']
    listed = (await client.get(PIPES, headers=auth('ana'))).json()['items']
    assert [p['name'] for p in listed] == ['Contactos', 'Comercial']
    templates = (await client.get(f'{PIPES}/templates', headers=auth('ana'))).json()['items']
    assert {t['key'] for t in templates} == {'tiktok_live', 'whatsapp', 'reactivation', 'blank'}
    assert (await client.patch(f'{PIPES}/{made["id"]}', headers=auth('ana'),
                               json={'name': 'Hack'})).status_code == 403
    renamed = await client.patch(f'{PIPES}/{made["id"]}', headers=auth('sup'), json={'name': 'Hernias'})
    assert renamed.json()['name'] == 'Hernias'
    # the built-in funnel mirrors the contact status: it is not edited
    default = listed[0]['id']
    assert (await client.patch(f'{PIPES}/{default}', headers=auth('sup'),
                               json={'name': 'X'})).status_code == 409
    assert (await client.put(f'{PIPES}/{default}/stages', headers=auth('sup'),
                             json={'stages': [{'name': 'Solo'}]})).status_code == 409


async def test_a_custom_funnel_holds_only_the_conversations_added_to_it(world):
    client, _ = world
    chat = await open_chat(client, CHAT_PHONE)
    other = await open_chat(client, '+51900000002', user='bea')
    await claim(client, chat)
    await claim(client, other, user='bea')
    funnel = await make_funnel(client)
    s1, s2, *_ = funnel['stages']
    board = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('ana'))).json()
    assert board['total'] == 0
    no_stage = await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('ana'), json={})
    assert no_stage.status_code == 422
    other_funnel = await make_funnel(client, name='Otro')
    wrong = await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('ana'),
                             json={'stage_id': other_funnel['stages'][0]['id']})
    assert wrong.status_code == 422                      # a stage of another funnel
    added = await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('ana'),
                             json={'stage_id': s1['id'], 'value_cents': 50000})
    assert added.status_code == 200 and added.json()['value_cents'] == 50000
    board = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('ana'))).json()
    assert column(board, s1['name'])['count'] == 1 and board['value_cents'] == 50000
    # bea does not see ana's card (not hers), the supervisor sees all
    assert (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('bea'))).json()['total'] == 0
    await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('ana'), json={'stage_id': s2['id']})
    board = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'))).json()
    assert column(board, s2['name'])['count'] == 1 and column(board, s1['name'])['count'] == 0
    assert column(board, s2['name'])['value_cents'] == 50000          # the value travels with the card
    mine = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'),
                             params={'mine': True})).json()
    assert mine['total'] == 0
    # it can be in several funnels, each with its own stage
    await client.put(f'{PIPES}/{other_funnel["id"]}/cards/{chat}', headers=auth('ana'),
                     json={'stage_id': other_funnel['stages'][0]['id']})
    of = (await client.get(f'{PIPES}/by-conversation/{chat}', headers=auth('ana'))).json()['items']
    assert [(i['name'], i['stage_id'] is not None) for i in of] == [
        ('Contactos', True), ('Comercial', True), ('Otro', True)]
    removed = await client.delete(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('ana'))
    assert removed.status_code == 204
    assert (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'))).json()['total'] == 0


async def test_columns_load_in_pages(world):
    client, factory = world
    funnel = await make_funnel(client, 'blank')
    first = funnel['stages'][0]['id']
    for n in range(32):
        phone = f'+5190100{n:04d}'
        chat = await open_chat(client, phone, user='sup')
        r = await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'),
                             json={'stage_id': first})
        assert r.status_code == 200, r.text
    board = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'))).json()
    col = board['stages'][0]
    assert col['count'] == 32 and len(col['cards']) == 30 and col['has_more'] is True
    more = (await client.get(f'{PIPES}/{funnel["id"]}/stages/{first}/cards', headers=auth('sup'),
                             params={'offset': 30})).json()
    assert len(more['cards']) == 2 and more['has_more'] is False
    assert {c['id'] for c in col['cards']}.isdisjoint({c['id'] for c in more['cards']})
    assert (await client.get(f'{PIPES}/{funnel["id"]}/stages/999999/cards',
                             headers=auth('sup'))).status_code == 404


async def test_stages_are_edited_as_a_whole_and_never_drop_conversations(world):
    client, _ = world
    funnel = await make_funnel(client, 'reactivation')
    stages = funnel['stages']
    chat = await open_chat(client, CHAT_PHONE, user='sup')
    await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'),
                     json={'stage_id': stages[1]['id']})
    payload = [{'id': stages[2]['id'], 'name': 'Agendó', 'color': '#22c55e'},
               {'id': stages[0]['id'], 'name': 'Sin respuesta', 'color': '#f59e0b', 'description': 'No contestó'},
               {'id': None, 'name': 'Nueva etapa', 'color': '#7c3aed'}]
    # the stage that still holds a conversation cannot be removed
    blocked = await client.put(f'{PIPES}/{funnel["id"]}/stages', headers=auth('sup'), json={'stages': payload})
    assert blocked.status_code == 409 and stages[1]['name'] in blocked.json()['detail']
    assert (await client.put(f'{PIPES}/{funnel["id"]}/stages', headers=auth('sup'), json={
        'stages': [{'name': 'x', 'color': 'red'}]})).status_code == 422
    assert (await client.put(f'{PIPES}/{funnel["id"]}/stages', headers=auth('sup'), json={
        'stages': [{'id': 99999, 'name': 'x'}]})).status_code == 422
    assert (await client.put(f'{PIPES}/{funnel["id"]}/stages', headers=auth('ana'),
                             json={'stages': payload})).status_code == 403
    payload.insert(1, {'id': stages[1]['id'], 'name': 'Reactivado', 'color': '#14b8a6'})
    saved = await client.put(f'{PIPES}/{funnel["id"]}/stages', headers=auth('sup'), json={'stages': payload})
    assert saved.status_code == 200, saved.text
    assert [s['name'] for s in saved.json()['stages']] == ['Agendó', 'Reactivado', 'Sin respuesta', 'Nueva etapa']
    # the conversation stayed where it was, under the renamed stage
    board = (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'))).json()
    assert column(board, 'Reactivado')['count'] == 1


async def test_the_numbers_come_from_the_moves(world):
    client, _ = world
    funnel = await make_funnel(client, 'reactivation')
    a, b, c = (s['id'] for s in funnel['stages'])
    for n in range(3):
        chat = await open_chat(client, f'+5190200000{n}', user='sup')
        await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'), json={'stage_id': a})
        if n < 2:
            await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'), json={'stage_id': b})
        if n < 1:
            await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'), json={'stage_id': c})
    rows = {i['stage_id']: i for i in (await client.get(
        f'{PIPES}/{funnel["id"]}/metrics', headers=auth('sup'))).json()['items']}
    assert (rows[a]['current'], rows[a]['entered']) == (1, 3)       # one still there, three came in
    assert (rows[b]['current'], rows[b]['entered']) == (1, 2)
    assert (rows[c]['current'], rows[c]['entered']) == (1, 1)


async def test_an_archived_funnel_disappears_and_its_conversations_stay(world):
    client, factory = world
    funnel = await make_funnel(client)
    chat = await open_chat(client, CHAT_PHONE, user='sup')
    await client.put(f'{PIPES}/{funnel["id"]}/cards/{chat}', headers=auth('sup'),
                     json={'stage_id': funnel['stages'][0]['id']})
    done = await client.patch(f'{PIPES}/{funnel["id"]}', headers=auth('sup'), json={'archived': True})
    assert done.status_code == 200
    assert [p['name'] for p in (await client.get(PIPES, headers=auth('sup'))).json()['items']] == ['Contactos']
    assert (await client.get(f'{PIPES}/{funnel["id"]}/board', headers=auth('sup'))).status_code == 404
    async with factory() as s:
        assert len((await s.scalars(select(cm.PipelineCard))).all()) == 1
