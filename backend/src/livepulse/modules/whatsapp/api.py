import base64
import io
import re
import warnings
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import aliased

from ...shared.db import get_session
from ..analytics.models import MonitorState, UserRole
from ..chat.models import ChatConversation, ChatMessage
from ..chat.service import aware
from ..crm.sites import site_ids_of, visible_to
from ..identity.roles import permissions_of
from ..social_live.contacts import claim
from ..social_live.models import CapturedPhone, Live, PhoneRegistry
from ..social_live.security import require_scope
from . import gateway, service

router = APIRouter(prefix='/api/whatsapp', tags=['WhatsApp mirror'])
reader = require_scope('wa:read')
sender = require_scope('wa:send')
manager = require_scope('wa:manage')


def can(who, permission):
    return permission in permissions_of(who.get('role'))


def item(conversation, registry=None):
    return {'id': conversation.id, 'phone': conversation.phone, 'name': conversation.contact_name,
            'registry_id': registry.id if registry else None,
            'advisor_id': registry.advisor_id if registry else conversation.advisor_id,
            'contact_status': registry.status if registry else None,
            'unread': conversation.unread, 'last_message_at': aware(conversation.last_message_at)}


def media_of(message):
    """The attachment of a message as the screen needs it, or None."""
    if not message.media_id:
        return None
    return {'kind': message.media_kind or 'image', 'seconds': message.media_seconds,
            'name': message.media_name, 'size': message.media_size}


def message_item(message):
    return {'id': message.id, 'direction': message.direction, 'author_kind': message.author_kind,
            'author_id': message.author_id, 'body': message.body, 'status': message.status,
            'error': message.error, 'at': aware(message.created_at),
            'has_image': bool(message.media_id) and (message.media_kind or 'image') == 'image',
            'media': media_of(message), 'media_unavailable': message.media_kind == service.NO_MEDIA,
            'sent_at': aware(message.sent_at), 'delivered_at': aware(message.delivered_at),
            'read_at': aware(message.read_at), 'observed_at': aware(message.observed_at)}


async def access(session, conversation_id, who, *, own=False):
    conversation = await session.get(ChatConversation, conversation_id, with_for_update=own)
    if not conversation or conversation.channel_id != service.CHANNEL:
        raise HTTPException(404, 'Conversación no encontrada.')
    registry = await service.registry_for(session, conversation, lock=own)
    owner = registry.advisor_id if registry else conversation.advisor_id
    if own and owner != who['user_id']:
        raise HTTPException(409, 'Toma el contacto antes de responder. Si tiene otra asesora, debe reasignarlo un supervisor.')
    if not own and not can(who, 'wa:read_all'):
        in_my_site = conversation.site_id is not None and conversation.site_id in await site_ids_of(
            session, who['user_id'])
        free = owner is None and conversation.site_id is None
        if owner != who['user_id'] and not free and not in_my_site:
            raise HTTPException(403, 'Esta conversación pertenece a otra asesora u otra sede.')
    return conversation, registry


@router.get('/status')
async def status(response: Response, who=Depends(reader), session=Depends(get_session)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        result = await gateway.call('/status')
    except gateway.GatewayUnavailable as exc:
        return {'state': 'unavailable', 'detail': str(exc)}
    if not can(who, 'wa:manage'):
        result.pop('qr', None)
    heartbeat = await session.get(MonitorState, 'whatsapp-worker')
    result['sync_at'] = aware(heartbeat.observed_at) if heartbeat else None
    result['sync_ok'] = bool(heartbeat and (service.now() - aware(heartbeat.observed_at)).total_seconds() < 90)
    return result


@router.post('/connect')
async def connect(response: Response, who=Depends(manager)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await gateway.call('/connect', {})
    except gateway.GatewayUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get('/conversations')
async def conversations(q: str = Query('', max_length=100), offset: int = Query(0, ge=0),
                        who=Depends(reader), session=Depends(get_session)):
    query = select(ChatConversation, PhoneRegistry).outerjoin(
        PhoneRegistry, PhoneRegistry.phone == ChatConversation.phone).where(
        ChatConversation.channel_id == service.CHANNEL)
    owner = case((PhoneRegistry.id.is_not(None), PhoneRegistry.advisor_id), else_=ChatConversation.advisor_id)
    if not can(who, 'wa:read_all'):
        query = query.where(visible_to(who['user_id'], owner))
    if q.strip():
        query = query.where(or_(ChatConversation.phone.contains(q.strip(), autoescape=True),
                               ChatConversation.contact_name.ilike('%' + q.replace('%', '').replace('_', '') + '%')))
    rows = (await session.execute(query.order_by(ChatConversation.last_message_at.desc().nullslast(),
                                                 ChatConversation.id.desc()).offset(offset).limit(51))).all()
    return {'items': [item(c, r) for c, r in rows[:50]], 'has_more': len(rows) > 50}


class OpenConversation(BaseModel):
    phone: str = Field(pattern=r'^\+[1-9]\d{7,14}$')


@router.post('/conversations')
async def open_conversation(body: OpenConversation, who=Depends(reader), session=Depends(get_session)):
    # Phone is explicit; never silently assume a country for international numbers.
    conversation = await service.conversation_for(session, body.phone)
    conversation, registry = await access(session, conversation.id, who)
    await session.commit()
    return item(conversation, registry)


@router.post('/conversations/{conversation_id}/claim')
async def take(conversation_id: int, who=Depends(sender), session=Depends(get_session)):
    conversation, registry = await access(session, conversation_id, who)
    if registry:
        await claim(session, registry.id, who['user_id'])
    else:
        result = await session.execute(update(ChatConversation).where(
            ChatConversation.id == conversation_id,
            or_(ChatConversation.advisor_id.is_(None), ChatConversation.advisor_id == who['user_id']))
            .values(advisor_id=who['user_id']))
        if result.rowcount != 1:
            raise HTTPException(409, 'Otra asesora tomó esta conversación.')
        await session.refresh(conversation)
    await session.commit()
    return item(conversation, registry)


@router.get('/conversations/{conversation_id}')
async def detail(conversation_id: int, before: int | None = Query(None, gt=0),
                 who=Depends(reader), session=Depends(get_session)):
    conversation, registry = await access(session, conversation_id, who)
    query = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
    if before:
        query = query.where(ChatMessage.id < before)
    messages = list((await session.scalars(query.order_by(ChatMessage.id.desc()).limit(101))).all())
    names = dict((await session.execute(select(UserRole.user_id, UserRole.display_name).where(
        UserRole.user_id.in_([m.author_id for m in messages if m.author_id])))).all())
    first_id = select(ChatMessage.id).where(
        ChatMessage.conversation_id == conversation.id, ChatMessage.direction == 'out',
        ChatMessage.sent_at >= CapturedPhone.captured_at).order_by(ChatMessage.sent_at, ChatMessage.id)
    first_id = first_id.limit(1).correlate(CapturedPhone).scalar_subquery()
    first_message = aliased(ChatMessage)
    next_reply = select(func.min(ChatMessage.created_at)).where(
        ChatMessage.conversation_id == conversation.id, ChatMessage.direction == 'in',
        ChatMessage.created_at > first_message.sent_at).correlate(first_message).scalar_subquery()
    # One query for the timeline, not two extra database round trips per LIVE on every poll.
    appearances = (await session.execute(select(CapturedPhone, Live, first_message, next_reply)
        .join(Live, Live.id == CapturedPhone.live_id).outerjoin(first_message, first_message.id == first_id)
        .where(CapturedPhone.phone == conversation.phone).order_by(CapturedPhone.captured_at.desc()).limit(100))).all()
    lives = []
    for appearance, live, first, reply in appearances:
        # First outgoing AFTER this appearance, never a message from an older LIVE.
        lives.append({'live_id': live.id, 'title': live.title, 'account_id': live.account_id,
            'tiktoker_id': live.tiktoker_id, 'captured_at': aware(appearance.captured_at),
            'sent_at': aware(first.sent_at) if first else None,
            'delivered_at': aware(first.delivered_at) if first else None,
            'read_at': aware(first.read_at) if first else None, 'next_inbound_at': aware(reply),
            'seconds_to_send': (aware(first.sent_at) - aware(appearance.captured_at)).total_seconds() if first else None,
            'author_id': first.author_id if first else None,
            'source': ('social_pulse' if first.author_kind == 'agent' else 'phone') if first else None})
    result = {**item(conversation, registry), 'messages': [
        {**message_item(m), 'author_name': names.get(m.author_id)} for m in reversed(messages[:100])],
              'has_more': len(messages) > 100, 'lives': lives}
    # Viewing in Social Pulse does not send a WhatsApp read receipt.
    return result


@router.post('/conversations/{conversation_id}/seen')
async def seen(conversation_id: int, who=Depends(sender), session=Depends(get_session)):
    conversation, _ = await access(session, conversation_id, who, own=True)
    conversation.unread = 0
    await session.commit()
    return {'ok': True}


class Outgoing(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=4000)


@router.post('/conversations/{conversation_id}/messages', status_code=202)
async def send(conversation_id: int, body: Outgoing, who=Depends(sender), session=Depends(get_session)):
    conversation, _ = await access(session, conversation_id, who, own=True)
    if not body.text.strip():
        raise HTTPException(422, 'Escribe un mensaje.')
    message = await service.queue_message(session, conversation, who['user_id'], str(body.request_id), body.text.strip())
    await session.commit()
    return message_item(message)


MAX_IMAGE = 8 * 1024 * 1024


@router.get('/messages/{message_id}/image')
async def image(message_id: int, who=Depends(reader), session=Depends(get_session)):
    message = await session.get(ChatMessage, message_id)
    if message is None or not message.media_id:
        raise HTTPException(404, 'Imagen no encontrada.')
    conversation, _ = await access(session, message.conversation_id, who)
    try:
        data = await gateway.call('/images/' + message.media_id)
        if data.get('phone') != conversation.phone:
            raise HTTPException(502, 'La imagen no corresponde a esta conversación.')
        if data.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
            raise HTTPException(502, 'Formato de imagen no compatible.')
        content = base64.b64decode(data['data'], validate=True)
        if len(content) > MAX_IMAGE:
            raise HTTPException(413, 'La imagen supera los 8 MB.')
    except gateway.GatewayUnavailable as exc:
        raise HTTPException(503, 'No se pudo recuperar la imagen. Reintenta; puede haber vencido en WhatsApp.') from exc
    return Response(content, media_type=data['mime'], headers={
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': 'inline'})


AUDIO = {'audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/webm', 'audio/wav', 'audio/amr'}
DOCUMENT = re.compile(r'^(application/(pdf|octet-stream|msword|rtf|zip|vnd\.ms-(excel|powerpoint)|'
                      r'vnd\.openxmlformats-officedocument\.[a-z.]+)|text/(plain|csv))$')
MB = 1024 * 1024
# kind -> (connector path, allowed types, size limit, shown in the page or downloaded)
MEDIA_RULES = {
    'image': ('/images/', {'image/jpeg', 'image/png', 'image/webp'}, 8 * MB, True),
    'sticker': ('/media/', {'image/webp'}, 1 * MB, True),
    'voice': ('/media/', AUDIO, 16 * MB, True),
    'audio': ('/media/', AUDIO, 16 * MB, True),
    'video': ('/media/', {'video/mp4', 'video/webm', 'video/3gpp'}, 24 * MB, True),
    'document': ('/media/', DOCUMENT, 24 * MB, False),
}


def byte_range(header, size):
    """A single `bytes=a-b` range (what audio and video players ask for), or None."""
    found = re.fullmatch(r'bytes=(\d*)-(\d*)', (header or '').strip())
    if not found or not (found.group(1) or found.group(2)):
        return None
    if found.group(1):
        start, end = int(found.group(1)), int(found.group(2)) if found.group(2) else size - 1
    else:
        start, end = max(0, size - int(found.group(2))), size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        raise HTTPException(416, 'Rango no válido.', headers={'Content-Range': f'bytes */{size}'})
    return start, end


@router.get('/messages/{message_id}/media')
async def media(message_id: int, request: Request, who=Depends(reader), session=Depends(get_session)):
    """The file of a message (image, voice note, audio, video, document, sticker), with the same
    access rule as the conversation. The type is checked here again, documents are only ever
    downloaded, and nothing is rendered from a type the browser could execute."""
    message = await session.get(ChatMessage, message_id)
    kind = (message.media_kind or 'image') if message is not None and message.media_id else None
    if kind not in MEDIA_RULES:
        raise HTTPException(404, 'Archivo no encontrado.')
    conversation, _ = await access(session, message.conversation_id, who)
    path, allowed, limit, inline = MEDIA_RULES[kind]
    try:
        data = await gateway.call(path + message.media_id)
    except gateway.GatewayUnavailable as exc:
        raise HTTPException(503, 'No se pudo recuperar el archivo. Reintenta; puede haber vencido en WhatsApp.') from exc
    mime = data.get('mime')
    if data.get('phone') != conversation.phone:
        raise HTTPException(502, 'El archivo no corresponde a esta conversación.')
    if not isinstance(mime, str) or (mime not in allowed if isinstance(allowed, set) else not allowed.match(mime)):
        raise HTTPException(502, 'Formato de archivo no compatible.')
    try:
        content = base64.b64decode(data['data'], validate=True)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(502, 'Archivo dañado.') from None
    if len(content) > limit:
        raise HTTPException(413, f'El archivo supera los {limit // MB} MB.')
    name = re.sub(r'[\x00-\x1f/\\\\"]', '_', message.media_name or 'documento')[:120]
    headers = {'Cache-Control': 'private, max-age=86400', 'X-Content-Type-Options': 'nosniff',
               'Cross-Origin-Resource-Policy': 'same-origin', 'Accept-Ranges': 'bytes',
               'Content-Disposition': 'inline' if inline else f"attachment; filename*=UTF-8''{quote(name)}"}
    window = byte_range(request.headers.get('range'), len(content)) if inline else None
    if window:
        start, end = window
        headers['Content-Range'] = f'bytes {start}-{end}/{len(content)}'
        return Response(content[start:end + 1], 206, media_type=mime, headers=headers)
    return Response(content, media_type=mime, headers=headers)


@router.post('/conversations/{conversation_id}/images', status_code=202)
async def send_image(conversation_id: int, request_id: Annotated[UUID, Form()],
                     file: Annotated[UploadFile, File()],
                     text: Annotated[str, Form(max_length=4000)] = '',
                     who=Depends(sender), session=Depends(get_session)):
    conversation, _ = await access(session, conversation_id, who, own=True)
    content = await file.read(MAX_IMAGE + 1)
    if len(content) > MAX_IMAGE:
        raise HTTPException(413, 'La imagen supera los 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as img:
                if img.format not in ('JPEG', 'PNG', 'WEBP') or img.width * img.height > 40_000_000:
                    raise ValueError
                img.verify()
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise HTTPException(422, 'Selecciona una imagen JPG, PNG o WebP válida (hasta 40 megapíxeles).') from None
    try:
        stored = await gateway.call('/images', {'phone': conversation.phone,
                                               'data': base64.b64encode(content).decode('ascii')})
    except gateway.GatewayUnavailable as exc:
        raise HTTPException(503, 'No se pudo guardar la imagen; vuelve a intentar.') from exc
    message = await service.queue_message(session, conversation, who['user_id'], str(request_id),
                                           text.strip(), media_id=stored['media_id'])
    await session.commit()
    return message_item(message)
