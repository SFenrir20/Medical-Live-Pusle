"""WhatsApp Cloud API (the official Meta API): the webhook Meta calls.

Meta calls this URL for two things:
  * GET  — once, when you save the webhook in the Meta app: it sends `hub.verify_token` (the text
           you chose, WA_CLOUD_VERIFY_TOKEN) and `hub.challenge`, and expects the challenge back;
  * POST — every incoming message and every delivery status, signed with the app secret
           (header X-Hub-Signature-256 = sha256 HMAC of the exact body).

Nothing is trusted without the signature. Messages and statuses are translated into the same
events the WhatsApp mirror produces and go through the same ingestion (conversations, CRM,
funnels, rules), so the inbox does not care which of the two delivered them. Replays are harmless:
each event gets a deterministic id derived from the Meta message id.

Not here yet (next steps): sending through the Cloud API, templates, and downloading media
(a photo or audio arrives as the same placeholder the mirror uses until then)."""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from ...shared.config import settings
from ...shared.db import get_session
from . import service

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/whatsapp-cloud', tags=['whatsapp-cloud'])
MAX_BODY = 1_000_000
MEDIA_LABEL = {'image': 'Imagen', 'video': 'Video', 'audio': 'Audio', 'voice': 'Audio',
               'document': 'Documento', 'sticker': 'Sticker'}


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    if not secret or not header or not header.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len('sha256='):].strip().lower())


def stamp(value) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc).isoformat()


def event_id(*parts) -> str:
    return str(uuid5(NAMESPACE_URL, 'wa-cloud:' + ':'.join(str(p) for p in parts)))


def text_of(message: dict) -> str:
    """What the conversation shows for a message. Media waits for its download (next step)."""
    kind = message.get('type')
    if kind == 'text':
        return (message.get('text') or {}).get('body') or ''
    if kind == 'button':
        return (message.get('button') or {}).get('text') or ''
    if kind == 'interactive':
        reply = message.get('interactive') or {}
        chosen = reply.get('button_reply') or reply.get('list_reply') or {}
        return chosen.get('title') or ''
    if kind in MEDIA_LABEL:
        data = message.get(kind) or {}
        caption = (data.get('caption') or '').strip()
        holder = f'[{MEDIA_LABEL[kind]}: consultar en el teléfono]'
        return f'{holder}\n{caption}' if caption else holder
    return '[Mensaje no textual: consultar en el teléfono]'


def events_of(payload: dict) -> list[dict]:
    """Every message and delivery status in a webhook delivery, as mirror events."""
    wanted = settings.wa_cloud_phone_number_id
    out: list[dict] = []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            value = change.get('value') or {}
            if change.get('field') != 'messages' or value.get('messaging_product') != 'whatsapp':
                continue
            if wanted and (value.get('metadata') or {}).get('phone_number_id') != wanted:
                continue                                    # another number of the same account
            names = {c.get('wa_id'): (c.get('profile') or {}).get('name')
                     for c in value.get('contacts') or []}
            for message in value.get('messages') or []:
                sender, wamid = message.get('from'), message.get('id')
                if not sender or not wamid:
                    continue
                event = {'id': event_id('message', wamid), 'type': 'message', 'phone': f'+{sender}',
                         'external_id': wamid, 'from_me': False, 'at': stamp(message.get('timestamp')),
                         'body': text_of(message)}
                if names.get(sender):
                    event['name'] = names[sender][:128]
                out.append(event)
            for status in value.get('statuses') or []:
                wamid, recipient, state = status.get('id'), status.get('recipient_id'), status.get('status')
                if not wamid or not recipient:
                    continue
                if state == 'failed':
                    log.warning('WhatsApp Cloud message failed (id=%s code=%s)', wamid,
                                ((status.get('errors') or [{}])[0]).get('code'))
                    continue
                if state not in ('sent', 'delivered', 'read'):
                    continue
                out.append({'id': event_id('status', wamid, state), 'type': 'receipt',
                            'phone': f'+{recipient}', 'external_id': wamid, 'status': state,
                            'at': stamp(status.get('timestamp')), 'clock': 'provider'})
    return out


@router.get('/webhook')
async def verify(mode: str | None = Query(None, alias='hub.mode'),
                 token: str | None = Query(None, alias='hub.verify_token'),
                 challenge: str | None = Query(None, alias='hub.challenge')):
    """Meta's handshake when the webhook is saved."""
    expected = settings.wa_cloud_verify_token
    if not expected:
        raise HTTPException(503, 'El webhook de WhatsApp Cloud no está configurado.')
    if mode != 'subscribe' or token is None or challenge is None \
            or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(403, 'Verificación rechazada.')
    return PlainTextResponse(challenge)


@router.post('/webhook')
async def receive(request: Request, session=Depends(get_session)):
    if not settings.wa_cloud_app_secret:
        raise HTTPException(503, 'El webhook de WhatsApp Cloud no está configurado.')
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, 'Cuerpo demasiado grande.')
    if not signature_ok(settings.wa_cloud_app_secret, body, request.headers.get('x-hub-signature-256')):
        raise HTTPException(403, 'Firma no válida.')
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, 'JSON no válido.') from None
    if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
        return Response(status_code=200)
    done = 0
    await service.ensure_channel(session)
    for event in events_of(payload):
        try:
            async with session.begin_nested():
                await service.ingest(session, event)
            done += 1
        except service.MirrorEventError as exc:
            # A bad item must not make Meta resend the whole delivery for days: it is skipped.
            log.warning('WhatsApp Cloud event skipped (reason=%s)', exc.code)
    await session.commit()
    return {'received': done}
