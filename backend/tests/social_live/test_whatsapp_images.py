import base64
import io
from uuid import uuid4

from PIL import Image
from sqlalchemy import select
from test_crm import CHAT_PHONE, NOW, auth, claim, open_chat

from livepulse.modules.chat.models import ChatMessage
from livepulse.modules.whatsapp import service as wa


def png():
    out = io.BytesIO()
    Image.new('RGB', (8, 8), color='blue').save(out, format='PNG')
    return out.getvalue()


async def test_image_upload_preview_ownership_and_idempotent_outbox(world, monkeypatch):
    client, factory = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    calls = []

    async def gateway(path, data=None):
        calls.append(path)
        if path == '/images':
            assert base64.b64decode(data['data']) == png()
            return {'media_id': 'a' * 64}
        if path.startswith('/images/'):
            return {'phone': CHAT_PHONE, 'mime': 'image/png',
                    'data': base64.b64encode(png()).decode()}
        if path == '/events':
            return []
        assert path == '/send' and data['media_id'] == 'a' * 64
        return {'state': 'sent', 'external_id': 'sent-image', 'at': NOW.isoformat()}

    monkeypatch.setattr(wa.gateway, 'call', gateway)
    path = f'/api/whatsapp/conversations/{chat}/images'
    data = {'request_id': str(uuid4()), 'text': 'Una imagen'}
    files = {'file': ('image.png', png(), 'image/png')}
    assert (await client.post(path, headers=auth('bea'), data=data, files=files)).status_code == 409
    assert calls == []
    first = await client.post(path, headers=auth('ana'), data=data, files=files)
    assert first.status_code == 202, first.text
    assert first.json()['has_image']
    repeated = await client.post(path, headers=auth('ana'), data=data, files=files)
    assert repeated.json()['id'] == first.json()['id']
    image_path = f"/api/whatsapp/messages/{first.json()['id']}/image"
    assert (await client.get(image_path, headers=auth('bea'))).status_code == 403
    picture = await client.get(image_path, headers=auth('jefa'))
    assert picture.content == png() and picture.headers['content-type'] == 'image/png'
    assert 'no-store' in picture.headers['cache-control']
    await wa.tick(factory)
    async with factory() as s:
        messages = (await s.scalars(select(ChatMessage))).all()
        assert len(messages) == 1 and messages[0].status == 'sent'
    assert calls.count('/send') == 1


async def test_rejects_fake_images_and_oversize_files_before_gateway(world, monkeypatch):
    client, _ = world
    chat = await open_chat(client, CHAT_PHONE)
    await claim(client, chat)
    async def forbidden(*args, **kwargs):
        raise AssertionError('Invalid files must not reach the connector')
    monkeypatch.setattr(wa.gateway, 'call', forbidden)
    for content, expected in [(b'<svg onload="alert(1)">', 422), (b'x' * (8 * 1024 * 1024 + 1), 413)]:
        response = await client.post(f'/api/whatsapp/conversations/{chat}/images', headers=auth('ana'),
            data={'request_id': str(uuid4())}, files={'file': ('photo.png', content, 'image/png')})
        assert response.status_code == expected


async def test_incoming_image_metadata_survives_ingestion_and_duplicate_events(world):
    client, factory = world
    event = {'id': str(uuid4()), 'type': 'message', 'phone': CHAT_PHONE,
             'external_id': 'incoming-image', 'from_me': False, 'at': NOW.isoformat(),
             'body': 'Mi imagen', 'media_id': 'b' * 64}
    async with factory() as s, s.begin():
        await wa.ingest(s, event)
    async with factory() as s, s.begin():
        await wa.ingest(s, {**event, 'id': str(uuid4())})
    chat = await open_chat(client, CHAT_PHONE)
    result = (await client.get(f'/api/whatsapp/conversations/{chat}', headers=auth('ana'))).json()
    assert len(result['messages']) == 1 and result['messages'][0]['has_image']
