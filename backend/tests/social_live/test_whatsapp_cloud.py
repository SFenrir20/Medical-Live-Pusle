"""WhatsApp Cloud API webhook: Meta's handshake, the signature on every delivery, messages and
statuses turned into conversations, and safe replays."""
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.chat.models import ChatMessage
from livepulse.modules.whatsapp.models import MirrorReceipt
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings

URL = '/api/whatsapp-cloud/webhook'
SECRET, VERIFY, NUMBER = 'app-secret-123', 'verify-me-please', '109876543210'


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(settings, 'wa_cloud_app_secret', SECRET)
    monkeypatch.setattr(settings, 'wa_cloud_verify_token', VERIFY)
    monkeypatch.setattr(settings, 'wa_cloud_phone_number_id', NUMBER)
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def verify(token):
        if token != 'sup':
            raise HTTPException(401)
        return {'id': 'sup', 'role': 'supervisor'}

    monkeypatch.setattr(clerk, 'verify_token', verify)


def sign(body: bytes, secret=SECRET) -> dict:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {'X-Hub-Signature-256': f'sha256={digest}', 'Content-Type': 'application/json'}


def delivery(*, messages=None, statuses=None, number=NUMBER):
    value = {'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': number,
                                                           'display_phone_number': '51900000000'}}
    if messages:
        value['messages'] = messages
        value['contacts'] = [{'wa_id': '51987654321', 'profile': {'name': 'Rosa Quispe'}}]
    if statuses:
        value['statuses'] = statuses
    return json.dumps({'object': 'whatsapp_business_account',
                       'entry': [{'id': 'waba', 'changes': [{'field': 'messages', 'value': value}]}]}).encode()


def text(wamid='wamid.AAA', body='Hola, quisiera una cita', at=1_800_000_000):
    return {'from': '51987654321', 'id': wamid, 'timestamp': str(at), 'type': 'text', 'text': {'body': body}}


async def post(client, body, headers=None):
    return await client.post(URL, content=body, headers=headers if headers is not None else sign(body))


async def test_meta_handshake_returns_the_challenge_only_with_the_right_token(env, cloud):
    client, _ = env
    ok = await client.get(URL, params={'hub.mode': 'subscribe', 'hub.verify_token': VERIFY,
                                       'hub.challenge': '1158201444'})
    assert ok.status_code == 200 and ok.text == '1158201444'
    for params in ({'hub.mode': 'subscribe', 'hub.verify_token': 'wrong', 'hub.challenge': '1'},
                   {'hub.mode': 'unsubscribe', 'hub.verify_token': VERIFY, 'hub.challenge': '1'},
                   {'hub.mode': 'subscribe', 'hub.verify_token': VERIFY},
                   {}):
        assert (await client.get(URL, params=params)).status_code == 403


async def test_nothing_is_accepted_until_it_is_configured(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(settings, 'wa_cloud_app_secret', '')
    monkeypatch.setattr(settings, 'wa_cloud_verify_token', '')
    assert (await client.get(URL, params={'hub.mode': 'subscribe', 'hub.verify_token': '',
                                          'hub.challenge': '1'})).status_code == 503
    assert (await post(client, delivery(messages=[text()]), {})).status_code == 503


async def test_a_delivery_without_a_valid_signature_is_refused(env, cloud):
    client, factory = env
    body = delivery(messages=[text()])
    assert (await post(client, body, {})).status_code == 403
    assert (await post(client, body, sign(body, 'another-secret'))).status_code == 403
    assert (await post(client, body, {'X-Hub-Signature-256': 'sha256=zz'})).status_code == 403
    tampered = sign(body)
    assert (await post(client, body + b' ', tampered)).status_code == 403
    async with factory() as s:
        assert (await s.scalars(select(ChatMessage))).all() == []


async def test_a_signed_message_becomes_a_conversation_and_a_replay_changes_nothing(env, cloud):
    client, factory = env
    body = delivery(messages=[text()])
    first = await post(client, body)
    assert first.status_code == 200 and first.json() == {'received': 1}
    assert (await post(client, body)).status_code == 200                    # Meta delivers it again
    async with factory() as s:
        rows = (await s.scalars(select(ChatMessage))).all()
        assert len(rows) == 1
        assert (rows[0].direction, rows[0].body, rows[0].external_id) == (
            'in', 'Hola, quisiera una cita', 'wamid.AAA')
    listed = (await client.get('/api/crm/conversations', headers={'Authorization': 'Bearer sup'})).json()
    item = listed['items'][0]
    assert (item['phone'], item['name'], item['unread']) == ('+51987654321', 'Rosa Quispe', 1)
    assert item['last']['body'] == 'Hola, quisiera una cita' and item['waiting'] is True


async def test_media_and_other_types_arrive_as_the_placeholders_the_inbox_understands(env, cloud):
    client, factory = env
    messages = [
        {'from': '51987654321', 'id': 'wamid.IMG', 'timestamp': '1800000001', 'type': 'image',
         'image': {'id': 'm1', 'caption': 'mi receta'}},
        {'from': '51987654321', 'id': 'wamid.AUD', 'timestamp': '1800000002', 'type': 'audio',
         'audio': {'id': 'm2'}},
        {'from': '51987654321', 'id': 'wamid.BTN', 'timestamp': '1800000003', 'type': 'button',
         'button': {'text': 'Sí, confirmo'}},
        {'from': '51987654321', 'id': 'wamid.LOC', 'timestamp': '1800000004', 'type': 'location',
         'location': {}},
    ]
    assert (await post(client, delivery(messages=messages))).json() == {'received': 4}
    async with factory() as s:
        bodies = {m.external_id: m.body for m in (await s.scalars(select(ChatMessage))).all()}
    assert bodies['wamid.IMG'] == '[Imagen: consultar en el teléfono]\nmi receta'
    assert bodies['wamid.AUD'] == '[Audio: consultar en el teléfono]'
    assert bodies['wamid.BTN'] == 'Sí, confirmo'
    assert bodies['wamid.LOC'].startswith('[Mensaje no textual')


async def test_delivery_statuses_are_recorded_even_before_the_message_is_known(env, cloud):
    client, factory = env
    statuses = [{'id': 'wamid.OUT', 'status': 'sent', 'timestamp': '1800000010', 'recipient_id': '51987654321'},
                {'id': 'wamid.OUT', 'status': 'read', 'timestamp': '1800000020', 'recipient_id': '51987654321'},
                {'id': 'wamid.OUT', 'status': 'failed', 'timestamp': '1800000030', 'recipient_id': '51987654321',
                 'errors': [{'code': 131047}]}]
    assert (await post(client, delivery(statuses=statuses))).json() == {'received': 2}   # failed is only logged
    async with factory() as s:
        receipt = await s.get(MirrorReceipt, 'wamid.OUT')
        assert receipt.sent_at is not None and receipt.read_at is not None and receipt.delivered_at is None
        assert receipt.read_clock == 'provider'


async def test_other_numbers_other_objects_and_garbage_are_ignored_without_failing(env, cloud):
    client, factory = env
    assert (await post(client, delivery(messages=[text()], number='555'))).json() == {'received': 0}
    instagram = json.dumps({'object': 'instagram', 'entry': []}).encode()
    assert (await post(client, instagram)).status_code == 200
    assert (await post(client, b'not json')).status_code == 400
    bad = delivery(messages=[{'from': 'abc', 'id': 'wamid.BAD', 'timestamp': '1', 'type': 'text',
                              'text': {'body': 'x'}}])
    assert (await post(client, bad)).json() == {'received': 0}       # an invalid phone skips the item only
    big = b'{' + b' ' * 1_100_000 + b'}'
    assert (await post(client, big)).status_code == 413
    async with factory() as s:
        assert (await s.scalars(select(ChatMessage))).all() == []
