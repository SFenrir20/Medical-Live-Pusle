from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from livepulse.modules.analytics.models import MonitorState
from livepulse.modules.chat.models import ChatConversation, ChatMessage
from livepulse.modules.social_live.models import (
    CapturedPhone,
    ContactAudit,
    Live,
    PhoneRegistry,
    TiktokAccount,
)
from livepulse.modules.whatsapp import gateway, service
from livepulse.modules.whatsapp.models import MirrorEvent, MirrorReceipt
from livepulse.shared import auth as clerk

PHONE = '+51900000001'
BASE = '/api/whatsapp'
T0 = datetime(2026, 11, 1, 15, tzinfo=timezone.utc)


def auth(user='ana'):
    return {'Authorization': f'Bearer {user}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)
    roles = {'ana': 'agente_ventas', 'bea': 'agente_ventas', 'jefa': 'jefe_marketing', 'sup': 'supervisor'}

    def verify(token):
        if token not in roles:
            raise HTTPException(401)
        return {'id': token, 'role': roles[token]}

    monkeypatch.setattr(clerk, 'verify_token', verify)


def event(kind='message', **kwargs):
    return {'id': str(uuid4()), 'type': kind, 'phone': PHONE, 'external_id': 'wa1',
            'at': T0.isoformat(), 'body': 'Hola', 'from_me': False, **kwargs}


async def ingest(factory, payload):
    async with factory() as session, session.begin():
        await service.ingest(session, payload)


async def open_chat(client, user='ana'):
    response = await client.post(f'{BASE}/conversations', headers=auth(user), json={'phone': PHONE})
    assert response.status_code == 200, response.text
    return response.json()['id']


async def claim_chat(client, conversation):
    response = await client.post(f'{BASE}/conversations/{conversation}/claim', headers=auth())
    assert response.status_code == 200, response.text


async def queue(client, conversation, request_id=None):
    response = await client.post(f'{BASE}/conversations/{conversation}/messages', headers=auth(),
                                json={'request_id': request_id or str(uuid4()), 'text': 'Buenos días'})
    assert response.status_code == 202, response.text
    return response.json()


async def test_mirror_deduplicates_messages_without_triggering_automation(env, people):
    client, factory = env
    first = event()
    await ingest(factory, first)
    await ingest(factory, first)  # commit succeeded but gateway ACK was lost
    await ingest(factory, {**first, 'id': str(uuid4())})  # provider replay
    async with factory() as session:
        conversation = await session.scalar(select(ChatConversation))
        assert conversation.unread == 1
        assert conversation.bot_active is False
        assert await session.scalar(select(func.count()).select_from(ChatMessage)) == 1


async def test_claim_permissions_and_idempotent_outbox(env, people):
    client, factory = env
    conversation = await open_chat(client)
    url = f'{BASE}/conversations/{conversation}'
    payload = {'request_id': str(uuid4()), 'text': 'Buenos días'}
    assert (await client.post(url + '/messages', headers=auth(), json=payload)).status_code == 409
    await claim_chat(client, conversation)
    assert (await client.post(url + '/claim', headers=auth('bea'))).status_code == 403
    assert (await client.get(url, headers=auth('bea'))).status_code == 403
    assert (await client.get(url, headers=auth('jefa'))).status_code == 200
    assert (await client.post(url + '/messages', headers=auth('jefa'), json=payload)).status_code == 403
    assert (await client.get(url, headers=auth('read-secret'))).status_code == 403
    a = await queue(client, conversation, payload['request_id'])
    b = await queue(client, conversation, payload['request_id'])
    assert a['id'] == b['id']
    assert a['status'] == 'queued' and a['sent_at'] is None
    assert (await client.post(url + '/messages', headers=auth(),
                             json={**payload, 'text': 'Otro contenido'})).status_code == 409


async def test_receipts_before_message_and_out_of_order_preserve_read_state(env, people):
    _, factory = env
    read_time = T0 + timedelta(seconds=30)
    await ingest(factory, event('receipt', status='read', at=read_time.isoformat(), clock='provider'))
    await ingest(factory, event(from_me=True))
    await ingest(factory, event('receipt', status='delivered', at=(T0 + timedelta(seconds=10)).isoformat(), clock='provider'))
    await ingest(factory, event('receipt', status='sent', at=T0.isoformat()))
    async with factory() as session:
        message = await session.scalar(select(ChatMessage))
        assert message.status == 'read'
        assert service.aware(message.read_at) == read_time
        assert message.author_kind == 'system' and message.author_id is None


async def test_late_live_capture_uses_existing_chat_and_registry_owner(env, people):
    client, factory = env
    await ingest(factory, event())
    conversation = await open_chat(client)
    await claim_chat(client, conversation)
    async with factory() as session, session.begin():
        session.add(PhoneRegistry(phone=PHONE, first_captured_at=T0, advisor_id='bea', status='new'))
    # Existing conversation ownership cannot override a newer central CRM assignment.
    assert (await client.get(f'{BASE}/conversations/{conversation}', headers=auth())).status_code == 403
    rows = (await client.get(f'{BASE}/conversations', headers=auth())).json()['items']
    assert not rows
    assert (await client.get(f'{BASE}/conversations/{conversation}', headers=auth('bea'))).status_code == 200


async def test_live_wait_time_ignores_messages_before_capture_and_keeps_manual_state(env, people):
    client, factory = env
    async with factory() as session, session.begin():
        session.add(TiktokAccount(id='medical', name='Medical', username='medical'))
        await session.flush()
        session.add_all([Live(id='morning', account_id='medical', started_at=T0, status='live'),
                         Live(id='afternoon', account_id='medical', started_at=T0 + timedelta(hours=4), status='live')])
        await session.flush()
        session.add(PhoneRegistry(phone=PHONE, first_live_id='morning', first_captured_at=T0,
                                  advisor_id='ana', status='new'))
        await session.flush()
        session.add_all([CapturedPhone(live_id='morning', phone=PHONE, source='comment', captured_at=T0, is_new=True),
                         CapturedPhone(live_id='afternoon', phone=PHONE, source='comment',
                                       captured_at=T0 + timedelta(hours=4), is_new=False)])
    await ingest(factory, event(from_me=True, at=(T0 - timedelta(hours=1)).isoformat(), external_id='old'))
    await ingest(factory, event(from_me=True, at=(T0 + timedelta(minutes=2)).isoformat(), external_id='morning-reply'))
    conversation = await open_chat(client)
    result = (await client.get(f'{BASE}/conversations/{conversation}', headers=auth())).json()
    assert result['contact_status'] == 'new'
    morning = next(row for row in result['lives'] if row['live_id'] == 'morning')
    afternoon = next(row for row in result['lives'] if row['live_id'] == 'afternoon')
    assert morning['seconds_to_send'] == 120 and morning['source'] == 'phone'
    assert afternoon['seconds_to_send'] is None


async def test_outbox_timeout_reuses_request_and_confirmation_resolves_ambiguity(env, people, monkeypatch):
    client, factory = env
    conversation = await open_chat(client)
    await claim_chat(client, conversation)
    request_id = str(uuid4())
    await queue(client, conversation, request_id)
    requests = []

    async def fake_call(path, data=None):
        if path == '/events':
            return []
        requests.append(data)
        if len(requests) == 1:
            raise gateway.GatewayUnavailable('timeout after server accepted')
        return {'state': 'unknown', 'external_id': 'out1'}

    monkeypatch.setattr(gateway, 'call', fake_call)
    with pytest.raises(gateway.GatewayUnavailable):
        await service.tick(factory)
    await service.tick(factory)
    assert requests[0] == requests[1] and requests[0]['request_id'] == request_id
    await service.tick(factory)
    assert len(requests) == 2  # unknown sends are NOT automatically resent
    await ingest(factory, event(from_me=True, request_id=request_id, external_id='out1'))
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ChatMessage)) == 1
        message = await session.scalar(select(ChatMessage))
        assert message.status == 'sent' and message.author_id == 'ana' and message.error is None


async def test_reassignment_cancels_unsent_queued_message(env, people, monkeypatch):
    client, factory = env
    conversation = await open_chat(client)
    await claim_chat(client, conversation)
    await queue(client, conversation)
    async with factory() as session, session.begin():
        row = await session.get(ChatConversation, conversation)
        row.advisor_id = 'bea'

    async def fake_call(path, data=None):
        assert path == '/events', 'Must not send after reassignment'
        return []

    monkeypatch.setattr(gateway, 'call', fake_call)
    await service.tick(factory)
    async with factory() as session:
        assert (await session.scalar(select(ChatMessage))).status == 'blocked'


async def test_slow_outbox_yields_to_inbound_sync_instead_of_blocking_a_whole_batch(env, people, monkeypatch):
    client, factory = env
    conversation = await open_chat(client)
    await claim_chat(client, conversation)
    await queue(client, conversation)
    await queue(client, conversation)
    clock = iter([0, 0, 46])
    monkeypatch.setattr(service, 'time', type('Clock', (), {'monotonic': staticmethod(lambda: next(clock))}))
    sent = []

    async def fake_call(path, data=None):
        if path == '/events':
            return []
        assert path == '/send'
        sent.append(data['request_id'])
        return {'state': 'sent', 'external_id': 'slow-send', 'at': T0.isoformat()}

    monkeypatch.setattr(gateway, 'call', fake_call)
    await service.tick(factory)
    assert len(sent) == 1
    async with factory() as session:
        statuses = list((await session.scalars(select(ChatMessage.status))).all())
        assert sorted(statuses) == ['queued', 'sent']


async def test_qr_is_restricted_and_not_cached(env, people, monkeypatch):
    client, _ = env

    async def fake_call(path, data=None):
        return {'state': 'qr', 'qr': 'private-qr'}

    monkeypatch.setattr(gateway, 'call', fake_call)
    response = await client.get(f'{BASE}/status', headers=auth())
    assert 'qr' not in response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert (await client.post(f'{BASE}/connect', headers=auth())).status_code == 403
    assert (await client.post(f'{BASE}/connect', headers=auth('sup'))).json()['qr'] == 'private-qr'


async def test_only_confirmed_agent_send_marks_contacted_with_audit(env, people, monkeypatch):
    client, factory = env
    async with factory() as session, session.begin():
        session.add(PhoneRegistry(phone=PHONE, first_captured_at=T0, advisor_id='ana', status='new'))
    conversation = await open_chat(client)
    request_id = str(uuid4())
    queued = await queue(client, conversation, request_id)
    async with factory() as session:
        assert (await session.scalar(select(PhoneRegistry))).status == 'new'
    sent_at = T0 + timedelta(minutes=5)

    async def fake_call(path, data=None):
        if path == '/events':
            return []
        return {'state': 'sent', 'external_id': 'confirmed', 'at': sent_at.isoformat()}

    monkeypatch.setattr(gateway, 'call', fake_call)
    await service.tick(factory)
    await ingest(factory, event(from_me=True, request_id=request_id, external_id='confirmed', at=sent_at.isoformat()))
    async with factory() as session:
        registry = await session.scalar(select(PhoneRegistry))
        assert registry.status == 'contacted' and service.aware(registry.contacted_at) == sent_at
        audits = (await session.scalars(select(ContactAudit).where(ContactAudit.action == 'whatsapp_sent'))).all()
        assert len(audits) == 1 and audits[0].actor == 'ana' and audits[0].value == str(queued['id'])


async def test_provider_clock_supersedes_observation_and_cannot_be_overwritten(env, people):
    _, factory = env
    await ingest(factory, event(from_me=True))
    await ingest(factory, event('receipt', status='read', clock='observed', at=(T0 + timedelta(seconds=10)).isoformat()))
    await ingest(factory, event('receipt', status='read', clock='provider', at=(T0 + timedelta(seconds=20)).isoformat()))
    await ingest(factory, event('receipt', status='read', clock='observed', at=(T0 + timedelta(seconds=5)).isoformat()))
    async with factory() as session:
        message = await session.scalar(select(ChatMessage))
        assert service.aware(message.read_at) == T0 + timedelta(seconds=20)


async def test_conflicting_receipt_preserved_without_blocking_next_message_or_send(env, people, monkeypatch, caplog):
    client, factory = env
    conversation = await open_chat(client)
    await claim_chat(client, conversation)
    await queue(client, conversation)
    await ingest(factory, event('receipt', status='delivered'))
    conflict = event('receipt', seq=11, status='read', phone='+51900000002')
    following = event(seq=12, external_id='next-message', body='Private content must not enter logs')
    calls = []

    async def fake_call(path, data=None):
        calls.append((path, data))
        if path == '/events':
            return [conflict, following]
        if path == '/send':
            return {'state': 'sent', 'external_id': 'sent-after-conflict', 'at': T0.isoformat()}
        return {'ok': True}

    monkeypatch.setattr(gateway, 'call', fake_call)
    await service.tick(factory)
    assert ('/events/quarantine', {'sequence': 11, 'reason': 'receipt_phone_mismatch'}) in calls
    assert ('/events/ack', {'sequences': [12]}) in calls
    assert ('/events/ack', {'sequences': [11]}) not in calls
    async with factory() as session:
        original = await session.get(MirrorReceipt, 'wa1')
        assert original.phone == PHONE and original.read_at is None
        assert await session.get(MirrorEvent, conflict['id']) is None
        assert await session.get(MirrorEvent, following['id']) is not None
        assert (await session.scalar(select(ChatMessage).where(ChatMessage.wa_request_id.is_not(None)))).status == 'sent'
        assert (await session.get(MonitorState, 'whatsapp-worker')).status == 'running'
    assert 'receipt_phone_mismatch' in caplog.text
    assert PHONE not in caplog.text and conflict['phone'] not in caplog.text
    assert following['body'] not in caplog.text


async def test_cannot_ack_or_continue_when_preservation_fails(env, people, monkeypatch):
    _, factory = env
    bad = event(seq=7, at='invalid private value')
    calls = []

    async def fake_call(path, data=None):
        calls.append(path)
        if path == '/events':
            return [bad, event(seq=8, external_id='later')]
        if path == '/events/quarantine':
            raise gateway.GatewayUnavailable('gateway unavailable or not upgraded')
        pytest.fail('Must not ACK an unpreserved event')

    monkeypatch.setattr(gateway, 'call', fake_call)
    with pytest.raises(gateway.GatewayUnavailable):
        await service.tick(factory)
    assert calls == ['/events', '/events/quarantine']
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ChatMessage)) == 0
        assert await session.get(MonitorState, 'whatsapp-worker') is None


async def test_transient_database_failure_is_retried_not_quarantined(env, monkeypatch):
    _, factory = env
    calls = []

    async def fake_call(path, data=None):
        calls.append(path)
        assert path == '/events'
        return [event(seq=1)]

    async def broken_ingest(session, payload):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(gateway, 'call', fake_call)
    monkeypatch.setattr(service, 'ingest', broken_ingest)
    with pytest.raises(RuntimeError):
        await service.tick(factory)
    assert calls == ['/events']


@pytest.mark.parametrize(('changes', 'reason'), [
    ({'at': 'private-invalid-date'}, 'invalid_timestamp'),
    ({'at': '2026-11-01T15:00:00'}, 'timestamp_without_timezone'),
    ({'at': None}, 'invalid_timestamp'),
    ({'at': '+010000-01-01T00:00:00.000Z'}, 'invalid_timestamp'),
    ({'phone': 'invalid-private-number'}, 'invalid_phone'),
    ({'phone': None}, 'invalid_phone'),
    ({'external_id': ''}, 'invalid_message_id'),
    ({'id': 'bad'}, 'invalid_event_id'),
    ({'type': 'unexpected'}, 'unknown_event_type'),
    ({'from_me': 'false'}, 'invalid_message_direction'),
    ({'body': None}, 'invalid_message_text'),
    ({'body': 'text\x00with-null'}, 'invalid_message_text'),
    ({'name': {'invalid': True}}, 'invalid_contact_name'),
    ({'request_id': 'bad'}, 'invalid_request_id'),
    ({'type': 'receipt', 'status': 'unknown'}, 'invalid_receipt_status'),
    ({'type': 'receipt', 'status': 'read', 'clock': 'unknown'}, 'invalid_receipt_clock'),
])
async def test_invalid_event_has_safe_reason_and_no_partial_writes(env, changes, reason):
    _, factory = env
    with pytest.raises(service.MirrorEventError, match=f'^{reason}$'):
        await ingest(factory, event(**changes))
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ChatMessage)) == 0
