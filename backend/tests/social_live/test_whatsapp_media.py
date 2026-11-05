"""Attachments of the WhatsApp mirror: what the screen is told, who may fetch the file, the checks
on the file itself, players asking for byte ranges, and recovery of old placeholder messages."""
import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.chat.models import ChatConversation, ChatMessage
from livepulse.modules.whatsapp import gateway, service
from livepulse.shared import auth as clerk

PHONE = '+51900000001'
BASE = '/api/whatsapp'
NOW = datetime.now(timezone.utc).replace(microsecond=0)
OGG = b'OggS' + bytes(range(60))
PDF = b'%PDF-1.7 ' + b'x' * 50


def auth(user):
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


class FakeConnector:
    """Stands in for the WhatsApp connector: files by id, and the old messages it still holds."""

    def __init__(self):
        self.files, self.adoptable, self.calls, self.down = {}, {}, [], False

    async def __call__(self, path, data=None):
        self.calls.append(path)
        if self.down:
            raise gateway.GatewayUnavailable('down')
        if path == '/media/adopt':
            return self.adoptable.get(data['external_id'], {'adopted': False, 'reason': 'not_stored'})
        name = path.rsplit('/', 1)[-1]
        if name not in self.files:
            raise gateway.GatewayUnavailable('missing')
        return self.files[name]


@pytest.fixture
def connector(monkeypatch):
    fake = FakeConnector()
    monkeypatch.setattr(gateway, 'call', fake)
    return fake


def event(**extra):
    return {'id': str(uuid4()), 'type': 'message', 'phone': PHONE, 'external_id': str(uuid4()),
            'at': NOW.isoformat(), 'body': '', 'from_me': False, **extra}


async def ingest(factory, payload):
    async with factory() as session, session.begin():
        await service.ingest(session, payload)


def file_record(mime, data, phone=PHONE):
    return {'phone': phone, 'mime': mime, 'data': base64.b64encode(data).decode()}


async def chat(client, user='ana'):
    r = await client.post(f'{BASE}/conversations', headers=auth(user), json={'phone': PHONE})
    assert r.status_code == 200, r.text
    return r.json()['id']


async def messages(client, conversation, user='ana'):
    r = await client.get(f'{BASE}/conversations/{conversation}', headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()['messages']


MEDIA_ID = 'a' * 64


async def test_each_attachment_reaches_the_screen_with_its_details(env, people, connector):
    client, factory = env
    await ingest(factory, event(media_id=MEDIA_ID, media_kind='voice', media_seconds=23))
    await ingest(factory, event(media_id='b' * 64, media_kind='document', media_name='receta.pdf',
                                media_size=4096, body='Mi receta'))
    # events queued before the connector knew about kinds only ever carried images
    await ingest(factory, event(media_id='c' * 64, body='[Imagen]'))
    await ingest(factory, event(body='hola'))
    conversation = await chat(client)
    voice, document, legacy, text = await messages(client, conversation)
    assert voice['media'] == {'kind': 'voice', 'seconds': 23, 'name': None, 'size': None}
    assert voice['has_image'] is False and voice['body'] == ''
    assert document['media'] == {'kind': 'document', 'seconds': None, 'name': 'receta.pdf', 'size': 4096}
    assert document['body'] == 'Mi receta'
    assert legacy['media']['kind'] == 'image' and legacy['has_image'] is True
    assert text['media'] is None and text['has_image'] is False


@pytest.mark.parametrize('extra, code', [
    ({'media_kind': 'executable'}, 'invalid_media_kind'),
    ({'media_seconds': -1}, 'invalid_media_details'),
    ({'media_seconds': True}, 'invalid_media_details'),
    ({'media_size': 'big'}, 'invalid_media_details'),
    ({'media_name': 'a\x00b.pdf'}, 'invalid_media_name'),
    ({'media_name': 'x' * 201}, 'invalid_media_name'),
])
async def test_malformed_attachment_details_are_quarantined_not_stored(env, people, extra, code):
    _, factory = env
    with pytest.raises(service.MirrorEventError) as problem:
        await ingest(factory, event(**{'media_id': MEDIA_ID, 'media_kind': 'audio', **extra}))
    assert problem.value.code == code
    async with factory() as session:
        assert (await session.scalars(select(ChatMessage))).all() == []


async def test_only_who_may_see_the_conversation_gets_the_file(env, people, connector):
    client, factory = env
    await ingest(factory, event(media_id=MEDIA_ID, media_kind='voice', media_seconds=5))
    conversation = await chat(client)
    await client.post(f'{BASE}/conversations/{conversation}/claim', headers=auth('ana'))
    message_id = (await messages(client, conversation))[0]['id']
    connector.files[MEDIA_ID] = file_record('audio/ogg', OGG)
    url = f'{BASE}/messages/{message_id}/media'
    mine = await client.get(url, headers=auth('ana'))
    assert mine.status_code == 200 and mine.content == OGG
    assert mine.headers['content-type'] == 'audio/ogg'
    assert mine.headers['content-disposition'] == 'inline'
    assert mine.headers['x-content-type-options'] == 'nosniff'
    assert 'max-age' in mine.headers['cache-control'] and 'no-store' not in mine.headers['cache-control']
    assert (await client.get(url, headers=auth('bea'))).status_code == 403     # another agent's chat
    assert (await client.get(url, headers=auth('jefa'))).status_code == 200    # reviewers may look
    assert (await client.get(url)).status_code == 401
    assert (await client.get(f'{BASE}/messages/99999/media', headers=auth('ana'))).status_code == 404


async def test_the_file_is_checked_again_before_it_reaches_the_browser(env, people, connector):
    client, factory = env
    await ingest(factory, event(media_id=MEDIA_ID, media_kind='voice'))
    await ingest(factory, event(media_id='b' * 64, media_kind='document', media_name='../../etc/pass"wd.pdf'))
    conversation = await chat(client)
    await client.post(f'{BASE}/conversations/{conversation}/claim', headers=auth('ana'))
    voice, document = await messages(client, conversation)
    voice_url = f'{BASE}/messages/{voice["id"]}/media'

    connector.files[MEDIA_ID] = file_record('audio/ogg', OGG, phone='+51922222222')
    assert (await client.get(voice_url, headers=auth('ana'))).status_code == 502   # bound to another contact
    connector.files[MEDIA_ID] = file_record('text/html', b'<script>alert(1)</script>')
    assert (await client.get(voice_url, headers=auth('ana'))).status_code == 502   # never page content
    connector.files[MEDIA_ID] = {'phone': PHONE, 'mime': 'audio/ogg', 'data': '###'}
    assert (await client.get(voice_url, headers=auth('ana'))).status_code == 502
    connector.files[MEDIA_ID] = file_record('audio/ogg', OGG)
    connector.down = True
    assert (await client.get(voice_url, headers=auth('ana'))).status_code == 503
    connector.down = False

    # a document is only ever downloaded, with a name that cannot escape a folder or a header
    connector.files['b' * 64] = file_record('application/pdf', PDF)
    pdf = await client.get(f'{BASE}/messages/{document["id"]}/media', headers=auth('ana'))
    assert pdf.status_code == 200 and pdf.headers['content-type'] == 'application/pdf'
    disposition = pdf.headers['content-disposition']
    assert disposition.startswith('attachment;') and '/' not in disposition.split("''")[1] and '"' not in disposition
    connector.files['b' * 64] = file_record('application/octet-stream', b'binary')
    assert (await client.get(f'{BASE}/messages/{document["id"]}/media', headers=auth('ana'))).status_code == 200
    connector.files['b' * 64] = file_record('video/mp4', b'x' * 10)
    assert (await client.get(f'{BASE}/messages/{document["id"]}/media', headers=auth('ana'))).status_code == 502


async def test_players_can_ask_for_part_of_the_file(env, people, connector):
    client, factory = env
    await ingest(factory, event(media_id=MEDIA_ID, media_kind='voice'))
    conversation = await chat(client)
    await client.post(f'{BASE}/conversations/{conversation}/claim', headers=auth('ana'))
    message_id = (await messages(client, conversation))[0]['id']
    connector.files[MEDIA_ID] = file_record('audio/ogg', OGG)
    url = f'{BASE}/messages/{message_id}/media'
    whole = await client.get(url, headers=auth('ana'))
    assert whole.headers['accept-ranges'] == 'bytes' and len(OGG) == 64
    part = await client.get(url, headers={**auth('ana'), 'Range': 'bytes=0-9'})
    assert part.status_code == 206 and part.content == OGG[:10]
    assert part.headers['content-range'] == 'bytes 0-9/64'
    tail = await client.get(url, headers={**auth('ana'), 'Range': 'bytes=60-'})
    assert tail.status_code == 206 and tail.content == OGG[60:]
    last = await client.get(url, headers={**auth('ana'), 'Range': 'bytes=-4'})
    assert last.content == OGG[-4:]
    beyond = await client.get(url, headers={**auth('ana'), 'Range': 'bytes=500-600'})
    assert beyond.status_code == 416 and beyond.headers['content-range'] == 'bytes */64'


async def test_the_conversation_list_names_the_attachment_and_who_is_waiting(env, people, connector):
    client, factory = env
    await ingest(factory, event(media_id=MEDIA_ID, media_kind='voice', media_seconds=41))
    conversation = await chat(client)
    await client.post(f'{BASE}/conversations/{conversation}/claim', headers=auth('ana'))
    item = (await client.get('/api/crm/conversations', headers=auth('ana'))).json()['items'][0]
    assert item['last']['kind'] == 'voice' and item['last']['seconds'] == 41 and item['waiting'] is True
    waiting = (await client.get('/api/crm/conversations', headers=auth('ana'), params={'scope': 'waiting'})).json()
    assert [i['id'] for i in waiting['items']] == [conversation] and waiting['counts']['waiting'] == 1

    async with factory() as session, session.begin():       # the agent answers
        session.add(ChatMessage(conversation_id=conversation, direction='out', author_kind='agent',
                                author_id='ana', body='Hola', status='sent',
                                created_at=NOW + timedelta(seconds=30)))
    answered = (await client.get('/api/crm/conversations', headers=auth('ana'))).json()
    assert answered['items'][0]['waiting'] is False and answered['counts']['waiting'] == 0
    other = await client.post(f'{BASE}/conversations', headers=auth('bea'), json={'phone': '+51900000002'})
    assert other.status_code == 200
    free = (await client.get('/api/crm/conversations', headers=auth('bea'), params={'scope': 'unassigned'})).json()
    assert free['counts']['unassigned'] == 1 and free['items'][0]['phone'] == '+51900000002'


async def test_old_placeholders_get_their_file_back_once(env, people, connector):
    client, factory = env
    old = NOW - timedelta(days=3)
    await ingest(factory, event(body='hola'))
    async with factory() as session, session.begin():
        convo = await session.scalar(select(ChatConversation))
        rows = {}
        for label, external in (('Audio', 'old-audio'), ('Documento', 'old-doc'), ('Imagen', 'old-photo'),
                                ('Video', 'old-gone'), ('Sticker', 'old-sticker')):
            message = ChatMessage(conversation_id=convo.id, direction='in', author_kind='contact',
                                  body=f'[{label}: consultar en el teléfono]', status='received',
                                  external_id=external, created_at=old)
            session.add(message)
            rows[external] = message
        session.add(ChatMessage(conversation_id=convo.id, direction='in', author_kind='contact',
                                body='[Ubicación: consultar en el teléfono]', status='received',
                                external_id='old-place', created_at=old))
        session.add(ChatMessage(conversation_id=convo.id, direction='in', author_kind='contact',
                                body='[Documento: consultar en el teléfono]\nMis exámenes', status='received',
                                external_id='old-captioned', created_at=old))
    connector.adoptable = {
        'old-audio': {'adopted': True, 'media_id': 'd' * 64, 'media_kind': 'voice', 'media_seconds': 19,
                      'media_name': None, 'media_size': 9000},
        'old-doc': {'adopted': True, 'media_id': 'e' * 64, 'media_kind': 'document', 'media_seconds': None,
                    'media_name': 'examenes.pdf', 'media_size': 1234},
        'old-captioned': {'adopted': True, 'media_id': 'f' * 64, 'media_kind': 'document',
                          'media_name': 'otro.pdf', 'media_size': 10},
        'old-photo': {'adopted': True, 'media_id': '1' * 64, 'media_kind': 'image'},
        'old-sticker': {'adopted': True, 'media_id': '2' * 64, 'media_kind': 'executable'},   # nonsense: not trusted
    }
    assert await service.adopt_old_media(factory) == 4
    async with factory() as session:
        by = {m.external_id: m for m in (await session.scalars(select(ChatMessage))).all()}
    assert (by['old-audio'].media_kind, by['old-audio'].media_seconds, by['old-audio'].body) == ('voice', 19, '')
    assert (by['old-doc'].media_name, by['old-doc'].media_size) == ('examenes.pdf', 1234)
    assert by['old-captioned'].body == 'Mis exámenes'                    # only what the sender wrote stays
    assert by['old-photo'].media_kind == 'image' and by['old-photo'].media_id == '1' * 64
    assert by['old-gone'].media_kind == service.NO_MEDIA and by['old-gone'].media_id is None
    assert by['old-sticker'].media_kind == service.NO_MEDIA              # an invalid answer is never stored
    assert by['old-place'].media_kind is None                            # not an attachment: never asked
    calls = len(connector.calls)
    assert await service.adopt_old_media(factory) == 0 and len(connector.calls) == calls   # asked once
    conversation_id = by['old-gone'].conversation_id
    await client.post(f'{BASE}/conversations/{conversation_id}/claim', headers=auth('ana'))
    shown = await messages(client, conversation_id)
    assert [m['media_unavailable'] for m in shown if m['body'].startswith('[Video')] == [True]
