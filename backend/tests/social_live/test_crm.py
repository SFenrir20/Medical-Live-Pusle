"""CRM over the WhatsApp conversations: visibility and ownership, one stage per contact, notes,
reassignment, consent, scheduled messages through the outbox, quick replies, contacts, summary."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.chat.models import ChatMessage, OptOut
from livepulse.modules.crm import models as cm
from livepulse.modules.crm.scheduled import tick as send_scheduled
from livepulse.modules.social_live.models import ContactAudit, PhoneRegistry
from livepulse.modules.whatsapp import service as wa
from livepulse.shared import auth as clerk

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
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


async def hear(factory, phone, text, external_id=None, name=None):
    async with factory() as s, s.begin():
        await wa.ingest(s, {'id': str(uuid4()), 'type': 'message', 'phone': phone,
                            'external_id': external_id or str(uuid4()), 'from_me': False,
                            'at': (NOW - timedelta(minutes=5)).isoformat(), 'body': text,
                            **({'name': name} if name else {})})


async def mine(client, conversation, user='ana', **body):
    r = await client.patch(f'{CRM}/conversations/{conversation}', headers=auth(user), json=body)
    return r


async def test_visibility_follows_ownership_and_roles(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await hear(factory, CHAT_PHONE, 'Hola, ¿tienen citas?', name='Rosa')
    ana = (await client.get(f'{CRM}/conversations', headers=auth('ana'))).json()
    assert [i['phone'] for i in ana['items']] == [CHAT_PHONE]      # free: visible to every agent
    assert ana['items'][0]['unread'] == 1 and ana['items'][0]['name'] == 'Rosa'
    assert ana['items'][0]['last']['body'] == 'Hola, ¿tienen citas?'
    assert ana['counts'] == {'all': 1, 'mine': 0, 'unread': 1, 'archived': 0}

    await claim(client, chat)
    bea = (await client.get(f'{CRM}/conversations', headers=auth('bea'))).json()
    assert bea['items'] == [] and bea['counts']['all'] == 0           # taken by ana
    assert (await client.get(f'{CRM}/conversations/{chat}', headers=auth('bea'))).status_code == 403
    for reviewer in ('sup', 'jefa'):
        seen = (await client.get(f'{CRM}/conversations', headers=auth(reviewer))).json()
        assert [i['phone'] for i in seen['items']] == [CHAT_PHONE]
    mine_scope = (await client.get(f'{CRM}/conversations', headers=auth('ana'),
                                   params={'scope': 'mine'})).json()
    assert mine_scope['counts']['mine'] == 1 and mine_scope['items'][0]['is_mine'] is True
    assert (await client.get(f'{CRM}/conversations')).status_code == 401


async def test_search_finds_contacts_and_message_text(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    await hear(factory, CHAT_PHONE, 'Quisiera saber del plan de financiamiento', name='Rosa Meza')
    await open_chat(client, LIVE_PHONE)

    async def found(q):
        data = (await client.get(f'{CRM}/conversations', headers=auth('sup'), params={'q': q})).json()
        return sorted(i['phone'] for i in data['items'])

    assert await found('financiamiento') == [CHAT_PHONE]      # inside a message
    assert await found('ROSA') == [CHAT_PHONE]                # name, any case
    assert await found('000001') == [CHAT_PHONE]              # part of the phone
    assert await found('camila') == [LIVE_PHONE]              # the TikTok user of the contact
    assert await found('nada que ver') == []
    assert await found('') == sorted([CHAT_PHONE, LIVE_PHONE])


async def test_only_the_owner_edits_and_the_stage_of_a_live_contact_is_its_status(world):
    client, factory = world
    chat = await open_chat(client, LIVE_PHONE)
    refused = await mine(client, chat, stage='contacted')           # free: must be taken first
    assert refused.status_code == 409 and 'Toma el contacto' in refused.json()['detail']
    await claim(client, chat)
    assert (await mine(client, chat, 'bea', stage='contacted')).status_code == 403   # not hers
    assert (await mine(client, chat, 'jefa', tags=['x'])).status_code == 403          # review only

    done = await mine(client, chat, stage='qualified', result='agendo',
                      tags=['  Compra ', 'Del Live', 'compra', ''])
    assert done.status_code == 200, done.text
    body = done.json()
    assert body['stage'] == 'qualified' and body['result'] == 'agendo'
    assert body['tags'] == ['Compra', 'Del Live', 'compra']
    async with factory() as s:
        contact = await s.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == LIVE_PHONE))
        assert contact.status == 'qualified' and contact.advisor_id == 'ana'   # ONE truth
        audit = (await s.scalars(select(ContactAudit).where(
            ContactAudit.registry_id == contact.id, ContactAudit.action == 'status'))).all()
        assert [(a.actor, a.value) for a in audit] == [('ana', 'qualified')]
    assert (await mine(client, chat, result='inventado')).status_code == 422
    assert (await mine(client, chat, result='')).json()['result'] is None


async def test_whatsapp_only_numbers_keep_their_stage_on_the_conversation(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    assert (await mine(client, chat, stage='contacted')).json()['stage'] == 'contacted'
    async with factory() as s:
        assert (await s.scalar(select(PhoneRegistry.id))) is not None     # only the LIVE contact
        assert await s.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == CHAT_PHONE)) is None


async def test_archive_unread_and_notes(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    await hear(factory, CHAT_PHONE, 'Hola')
    assert (await client.post(f'{CRM}/conversations/{chat}/notes', headers=auth('ana'),
                              json={'body': 'Prefiere hablar por la tarde'})).status_code == 201
    note = (await client.get(f'{CRM}/conversations/{chat}', headers=auth('ana'))).json()['notes'][0]
    assert note['body'] == 'Prefiere hablar por la tarde' and note['author_name'] == 'Ana'
    assert (await client.post(f'{CRM}/conversations/{chat}/notes', headers=auth('jefa'),
                              json={'body': 'x'})).status_code == 403
    assert (await client.delete(f'{CRM}/notes/{note["id"]}', headers=auth('bea'))).status_code == 403

    await client.post(f'{WA}/conversations/{chat}/seen', headers=auth('ana'))
    read = (await client.get(f'{CRM}/conversations', headers=auth('ana'))).json()
    assert read['counts']['unread'] == 0
    unread = (await client.post(f'{CRM}/conversations/{chat}/unread', headers=auth('ana'))).json()
    assert unread['unread'] == 1

    await mine(client, chat, archived=True)
    default = (await client.get(f'{CRM}/conversations', headers=auth('ana'))).json()
    assert default['items'] == [] and default['counts']['archived'] == 1
    archived = (await client.get(f'{CRM}/conversations', headers=auth('ana'),
                                 params={'scope': 'archived'})).json()
    assert [i['phone'] for i in archived['items']] == [CHAT_PHONE]
    await mine(client, chat, archived=False)
    assert (await client.delete(f'{CRM}/notes/{note["id"]}', headers=auth('sup'))).status_code == 200


async def test_supervisor_reassigns_and_the_old_owner_loses_access(world):
    client, factory = world
    chat = await open_chat(client, LIVE_PHONE)
    await claim(client, chat)
    body = {'advisor_id': 'bea'}
    assert (await client.post(f'{CRM}/conversations/{chat}/assign', headers=auth('ana'),
                              json=body)).status_code == 403
    assert (await client.post(f'{CRM}/conversations/{chat}/assign', headers=auth('sup'),
                              json={'advisor_id': 'nadie'})).status_code == 422
    moved = await client.post(f'{CRM}/conversations/{chat}/assign', headers=auth('sup'), json=body)
    assert moved.status_code == 200 and moved.json()['advisor_id'] == 'bea'
    assert (await client.get(f'{CRM}/conversations/{chat}', headers=auth('ana'))).status_code == 403
    assert (await client.get(f'{CRM}/conversations/{chat}', headers=auth('bea'))).status_code == 200
    freed = await client.post(f'{CRM}/conversations/{chat}/assign', headers=auth('sup'),
                              json={'advisor_id': None})
    assert freed.json()['advisor_id'] is None


async def test_consent_gates_campaigns_and_revoking_means_never_again(world):
    client, factory = world
    chat = await open_chat(client, LIVE_PHONE)
    await claim(client, chat)
    item = (await client.get(f'{CRM}/conversations/{chat}', headers=auth('ana'))).json()
    assert item['consent'] == 'unknown'
    granted = await client.put(f'{CRM}/conversations/{chat}/consent', headers=auth('ana'),
                               json={'status': 'granted', 'note': 'Lo pidió por chat'})
    assert granted.json()['consent'] == 'granted' and granted.json()['consent_note'] == 'Lo pidió por chat'
    summary = (await client.get(f'{CRM}/summary', headers=auth('ana'))).json()
    assert summary['ready_for_whatsapp'] == 1
    revoked = await client.put(f'{CRM}/conversations/{chat}/consent', headers=auth('ana'),
                               json={'status': 'revoked'})
    assert revoked.json()['consent'] == 'revoked' and revoked.json()['opted_out'] is True
    async with factory() as s:
        assert await s.get(OptOut, LIVE_PHONE) is not None
    again = await client.put(f'{CRM}/conversations/{chat}/consent', headers=auth('ana'),
                             json={'status': 'granted'})
    assert again.status_code == 409                       # she asked not to be written to
    assert (await client.get(f'{CRM}/summary', headers=auth('ana'))).json()['ready_for_whatsapp'] == 0


async def test_scheduled_messages_use_the_outbox_and_respect_ownership(world):
    client, factory = world
    chat = await open_chat(client, LIVE_PHONE)
    body = {'text': 'Te recuerdo tu cita de mañana', 'send_at': (NOW + timedelta(minutes=5)).isoformat()}
    assert (await client.post(f'{CRM}/conversations/{chat}/scheduled', headers=auth('ana'),
                              json=body)).status_code == 409                # not hers yet
    await claim(client, chat)
    assert (await client.post(f'{CRM}/conversations/{chat}/scheduled', headers=auth('jefa'),
                              json=body)).status_code == 403
    for bad in (NOW - timedelta(minutes=1), NOW + timedelta(days=45)):
        wrong = await client.post(f'{CRM}/conversations/{chat}/scheduled', headers=auth('ana'),
                                  json={**body, 'send_at': bad.isoformat()})
        assert wrong.status_code == 422
    made = await client.post(f'{CRM}/conversations/{chat}/scheduled', headers=auth('ana'), json=body)
    assert made.status_code == 201 and made.json()['scheduled'][0]['status'] == 'pending'

    assert await send_scheduled(factory, NOW + timedelta(minutes=1)) == 0      # too soon
    assert await send_scheduled(factory, NOW + timedelta(minutes=6)) == 1
    async with factory() as s:
        queued = (await s.scalars(select(ChatMessage).where(ChatMessage.direction == 'out'))).all()
        assert [(m.body, m.status, m.author_id) for m in queued] == [
            ('Te recuerdo tu cita de mañana', 'queued', 'ana')]
        assert queued[0].wa_request_id                                    # same outbox as a manual send
    done = (await client.get(f'{CRM}/conversations/{chat}', headers=auth('ana'))).json()
    assert done['scheduled'][0]['status'] == 'queued'

    # a second one, but the contact is reassigned before it goes out: nothing leaves under her name
    again = await client.post(f'{CRM}/conversations/{chat}/scheduled', headers=auth('ana'),
                              json={**body, 'text': 'Segundo', 'send_at': (NOW + timedelta(minutes=9)).isoformat()})
    sid = [s for s in again.json()['scheduled'] if s['status'] == 'pending'][0]['id']
    await client.post(f'{CRM}/conversations/{chat}/assign', headers=auth('sup'), json={'advisor_id': 'bea'})
    assert await send_scheduled(factory, NOW + timedelta(minutes=10)) == 0
    async with factory() as s:
        item = await s.get(cm.ChatScheduled, sid)
        assert item.status == 'cancelled' and 'cambió de asesor' in item.detail
        assert len((await s.scalars(select(ChatMessage).where(ChatMessage.direction == 'out'))).all()) == 1

    # and she can cancel one herself
    chat2 = await open_chat(client, CHAT_PHONE, 'bea')
    await claim(client, chat2, 'bea')
    made = await client.post(f'{CRM}/conversations/{chat2}/scheduled', headers=auth('bea'), json=body)
    sid = made.json()['scheduled'][0]['id']
    assert (await client.delete(f'{CRM}/scheduled/{sid}', headers=auth('ana'))).status_code == 403
    cancelled = await client.delete(f'{CRM}/scheduled/{sid}', headers=auth('bea'))
    assert cancelled.status_code == 200 and cancelled.json()['scheduled'] == []
    assert await send_scheduled(factory, NOW + timedelta(minutes=30)) == 0


async def test_quick_replies_are_managed_by_supervisors_and_used_by_everyone(world):
    client, _ = world
    new = {'title': 'Precio de la valoración', 'shortcut': '/Precio', 'body': 'Hola {{nombre|}}, cuesta S/ 80.'}
    assert (await client.post(f'{CRM}/quick-replies', headers=auth('ana'), json=new)).status_code == 403
    made = await client.post(f'{CRM}/quick-replies', headers=auth('sup'), json=new)
    assert made.status_code == 201 and made.json()['shortcut'] == 'precio'
    assert (await client.post(f'{CRM}/quick-replies', headers=auth('sup'),
                              json={**new, 'title': 'Otro'})).status_code == 409
    assert (await client.post(f'{CRM}/quick-replies', headers=auth('sup'),
                              json={**new, 'shortcut': 'con espacio'})).status_code == 422
    reply_id = made.json()['id']
    await client.put(f'{CRM}/quick-replies/{reply_id}', headers=auth('sup'), json={**new, 'active': False})
    assert (await client.get(f'{CRM}/quick-replies', headers=auth('ana'))).json()['items'] == []
    everything = await client.get(f'{CRM}/quick-replies', headers=auth('sup'), params={'all': True})
    assert [r['shortcut'] for r in everything.json()['items']] == ['precio']
    await client.put(f'{CRM}/quick-replies/{reply_id}', headers=auth('sup'), json=new)
    assert [r['shortcut'] for r in (await client.get(
        f'{CRM}/quick-replies', headers=auth('bea'))).json()['items']] == ['precio']
    assert (await client.delete(f'{CRM}/quick-replies/{reply_id}', headers=auth('ana'))).status_code == 403
    assert (await client.delete(f'{CRM}/quick-replies/{reply_id}', headers=auth('sup'))).status_code == 204


async def test_contacts_table_mixes_live_contacts_and_whatsapp_numbers(world):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    await hear(factory, CHAT_PHONE, 'Buenas tardes', name='Rosa')
    rows = (await client.get(f'{CRM}/contacts', headers=auth('sup'))).json()['items']
    by_phone = {r['phone']: r for r in rows}
    assert set(by_phone) == {LIVE_PHONE, CHAT_PHONE}
    live, chat_only = by_phone[LIVE_PHONE], by_phone[CHAT_PHONE]
    assert live['conversation_id'] is None and live['origin'] == 'tiktok_live'
    assert 'me interesa el precio' in live['message'] and live['stage'] == 'new'
    assert chat_only['origin'] == 'whatsapp' and chat_only['message'] == 'Buenas tardes'
    assert chat_only['conversation_id'] == chat and chat_only['advisor_name'] == 'Ana'

    only_new = (await client.get(f'{CRM}/contacts', headers=auth('sup'), params={'stage': 'contacted'})).json()
    assert only_new['items'] == []
    await mine(client, chat, stage='contacted')
    contacted = (await client.get(f'{CRM}/contacts', headers=auth('sup'), params={'stage': 'contacted'})).json()
    assert [r['phone'] for r in contacted['items']] == [CHAT_PHONE]
    found = (await client.get(f'{CRM}/contacts', headers=auth('sup'), params={'q': 'camila'})).json()
    assert [r['phone'] for r in found['items']] == [LIVE_PHONE]
    # an agent sees what is hers or free, not what another agent holds
    bea = (await client.get(f'{CRM}/contacts', headers=auth('bea'))).json()['items']
    assert [r['phone'] for r in bea] == [LIVE_PHONE]


async def test_summary_counts_and_what_each_role_may_see(world):
    client, _ = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    agent = (await client.get(f'{CRM}/summary', headers=auth('ana'))).json()
    assert agent['contacts'] == 1 and agent['conversations'] == 1
    assert agent['campaigns'] is None and agent['automations'] is None     # not for agents
    boss = (await client.get(f'{CRM}/summary', headers=auth('jefa'))).json()
    assert boss['campaigns'] == 0 and boss['automations'] == 0


async def test_live_metrics_expose_the_audience_watching_now(world):
    client, _ = world
    r = await client.post(f'{API}/lives/L1/events', headers=INGEST, json={
        'event_type': 'viewer', 'value': 42, 'timestamp': (NOW - timedelta(minutes=1)).isoformat()})
    assert r.status_code == 200, r.text
    metrics = (await client.get('/api/marketing/tiktok/lives/L1/metrics', headers=READ)).json()
    assert metrics['current_viewers'] == 42 and metrics['peak_viewers'] == 42


async def test_campaign_audience_defaults_to_people_who_agreed(world):
    from livepulse.modules.automation import broadcasts
    client, factory = world
    chat = await open_chat(client, LIVE_PHONE)
    await claim(client, chat)

    async def audience(**filters):
        async with factory() as s:
            return (await broadcasts.preview(s, {'statuses': ['new'], **filters}))['count']

    assert await audience() == 0                                   # nobody agreed yet
    assert await audience(require_consent=False) == 1
    await client.put(f'{CRM}/conversations/{chat}/consent', headers=auth('ana'),
                     json={'status': 'granted'})
    assert await audience() == 1
    await client.put(f'{CRM}/conversations/{chat}/consent', headers=auth('ana'),
                     json={'status': 'revoked'})
    assert await audience() == 0 and await audience(require_consent=False) == 0   # opted out too


async def test_agents_see_active_live_card_without_marketing_history_access(world):
    client, _ = world
    response = await client.get(f'{CRM}/active-lives', headers=auth('ana'))
    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1 and items[0]['id'] == 'L1'
    assert set(items[0]) == {'id', 'status', 'account', 'tiktoker', 'started_at', 'metrics'}
    assert set(items[0]['metrics']) == {'current_viewers', 'phones_captured'}
    assert (await client.get('/api/marketing/tiktok/lives', headers=auth('ana'))).status_code == 403
    assert (await client.get(f'{CRM}/active-lives')).status_code == 401
    assert (await client.get(f'{CRM}/active-lives', headers=auth('jefa'))).status_code == 200
