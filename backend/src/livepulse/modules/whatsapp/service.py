"""Real mirror transport, independent of simulator/bots. All sends pass through an outbox."""
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..analytics.models import MonitorState
from ..chat.models import ChatChannel, ChatConversation, ChatMessage
from ..chat.service import aware, get_conversation
from ..social_live.contacts import set_status
from ..social_live.models import ContactAudit, PhoneRegistry
from . import gateway
from .models import MirrorEvent, MirrorReceipt

CHANNEL = 'whatsapp-principal'
logger = logging.getLogger(__name__)


class MirrorEventError(ValueError):
    """A permanent event problem, identified without logging contact data or message text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def now():
    return datetime.now(timezone.utc)


def parse_time(value):
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise MirrorEventError('timestamp_without_timezone')
        return result.astimezone(timezone.utc)
    except MirrorEventError:
        raise
    except (ValueError, TypeError, OverflowError):
        raise MirrorEventError('invalid_timestamp') from None


def validate_event(event):
    if not isinstance(event, dict):
        raise MirrorEventError('invalid_event')
    try:
        if not isinstance(event.get('id'), str) or len(event['id']) != 36:
            raise ValueError
        UUID(event['id'])
    except ValueError:
        raise MirrorEventError('invalid_event_id') from None
    phone = event.get('phone')
    if not isinstance(phone, str) or not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        raise MirrorEventError('invalid_phone')
    external_id = event.get('external_id')
    if not isinstance(external_id, str) or not 1 <= len(external_id) <= 128 or '\x00' in external_id:
        raise MirrorEventError('invalid_message_id')
    if event.get('type') == 'receipt':
        if event.get('status') not in ('sent', 'delivered', 'read'):
            raise MirrorEventError('invalid_receipt_status')
        if event.get('clock', 'observed') not in ('provider', 'observed'):
            raise MirrorEventError('invalid_receipt_clock')
    elif event.get('type') == 'message':
        if not isinstance(event.get('from_me'), bool):
            raise MirrorEventError('invalid_message_direction')
        body = event.get('body')
        if not isinstance(body, str) or '\x00' in body:
            raise MirrorEventError('invalid_message_text')
        name = event.get('name')
        if name is not None and (not isinstance(name, str) or '\x00' in name):
            raise MirrorEventError('invalid_contact_name')
        request_id = event.get('request_id')
        if request_id is not None:
            try:
                if not isinstance(request_id, str) or len(request_id) != 36:
                    raise ValueError
                UUID(request_id)
            except ValueError:
                raise MirrorEventError('invalid_request_id') from None
    else:
        raise MirrorEventError('unknown_event_type')
    return parse_time(event.get('at'))


async def ensure_channel(session):
    channel = await session.get(ChatChannel, CHANNEL)
    if channel is None:
        try:
            async with session.begin_nested():
                session.add(ChatChannel(id=CHANNEL, kind='whatsapp_mirror', name='WhatsApp principal',
                                        status='active', policy={}))
                await session.flush()
        except IntegrityError:
            pass


async def registry_for(session, conversation, *, lock=False):
    query = select(PhoneRegistry).where(PhoneRegistry.phone == conversation.phone)
    if lock:
        query = query.with_for_update()
    registry = await session.scalar(query)
    # Match even if WhatsApp arrived before the LIVE captured the phone.
    if registry:
        conversation.registry_id = registry.id
    return registry


async def conversation_for(session, phone, name=None):
    await ensure_channel(session)
    conversation = await get_conversation(session, CHANNEL, phone, name=name)
    conversation.bot_active = False
    await registry_for(session, conversation)
    return conversation


async def apply_receipt(session, message):
    if not message.external_id or message.direction != 'out':
        return
    receipt = await session.get(MirrorReceipt, message.external_id)
    if not receipt:
        return
    conversation = await session.get(ChatConversation, message.conversation_id)
    if receipt.phone != conversation.phone:
        return
    for field in ('sent_at', 'delivered_at', 'read_at'):
        value = getattr(receipt, field)
        if value and (field != 'sent_at' or not getattr(message, field) or aware(value) < aware(getattr(message, field))):
            setattr(message, field, value)
    if message.read_at:
        message.status = 'read'
    elif message.delivered_at:
        message.status = 'delivered'
    elif message.sent_at:
        message.status = 'sent'
    if message.status in ('sent', 'delivered', 'read'):
        message.error = None


async def record_contact(session, message):
    """An actual agent send is evidence; queue insertion and device messages are not attribution."""
    if message.author_kind != 'agent' or not message.sent_at:
        return
    conversation = await session.get(ChatConversation, message.conversation_id)
    registry = await registry_for(session, conversation, lock=True)
    if (not registry or registry.status != 'new' or registry.advisor_id != message.author_id
            or aware(message.sent_at) < aware(registry.first_captured_at)):
        return
    await set_status(session, registry.id, message.author_id, 'contacted', contacted_at=message.sent_at)
    session.add(ContactAudit(registry_id=registry.id, actor=message.author_id, action='whatsapp_sent',
                             value=str(message.id), created_at=now()))


async def ingest(session, event):
    at = validate_event(event)
    if await session.get(MirrorEvent, event['id']):
        return
    phone = event['phone']
    external_id = event['external_id']
    if event['type'] == 'receipt':
        receipt = await session.get(MirrorReceipt, external_id)
        if receipt is None:
            receipt = MirrorReceipt(external_id=external_id, phone=phone)
            session.add(receipt)
        if receipt.phone != phone:
            raise MirrorEventError('receipt_phone_mismatch')
        field = {'sent': 'sent_at', 'delivered': 'delivered_at', 'read': 'read_at'}[event['status']]
        clock_field = {'delivered_at': 'delivered_clock', 'read_at': 'read_clock'}.get(field)
        old = getattr(receipt, field)
        clock = event.get('clock', 'observed')
        old_clock = getattr(receipt, clock_field) if clock_field else clock
        if (old is None or (old_clock != 'provider' and clock == 'provider')
                or (old_clock == clock and at < aware(old))):
            setattr(receipt, field, at)
            if clock_field:
                setattr(receipt, clock_field, clock)
        await session.flush()
        message = await session.scalar(select(ChatMessage).join(ChatConversation).where(
            ChatConversation.channel_id == CHANNEL, ChatConversation.phone == phone,
            ChatMessage.external_id == external_id))
        if message:
            await apply_receipt(session, message)
            await record_contact(session, message)
    elif event['type'] == 'message':
        conversation = await conversation_for(session, phone, event.get('name'))
        message = await session.scalar(select(ChatMessage).where(
            ChatMessage.conversation_id == conversation.id, ChatMessage.external_id == external_id))
        request_id = event.get('request_id')
        if message is None and request_id and event['from_me']:
            message = await session.scalar(select(ChatMessage).where(ChatMessage.wa_request_id == request_id))
            if message and message.conversation_id != conversation.id:
                raise MirrorEventError('outgoing_conversation_mismatch')
        if message is None:
            message = ChatMessage(conversation_id=conversation.id,
                direction='out' if event['from_me'] else 'in',
                author_kind='system' if event['from_me'] else 'contact',
                body=event['body'], status='sent' if event['from_me'] else 'received',
                created_at=at, observed_at=now(), external_id=external_id)
            session.add(message)
            if not event['from_me']:
                conversation.unread += 1
                if not conversation.last_inbound_at or at > aware(conversation.last_inbound_at):
                    conversation.last_inbound_at = at
        message.external_id = external_id
        if event['from_me']:
            message.sent_at = message.sent_at or at
            if message.status not in ('delivered', 'read'):
                message.status = 'sent'
            message.error = None
        if not conversation.last_message_at or at > aware(conversation.last_message_at):
            conversation.last_message_at = at
        await session.flush()
        await apply_receipt(session, message)
        await record_contact(session, message)
    else:
        raise MirrorEventError('unknown_event_type')
    session.add(MirrorEvent(id=event['id']))


async def queue_message(session, conversation, actor, request_id, text):
    previous = await session.scalar(select(ChatMessage).where(ChatMessage.wa_request_id == request_id))
    if previous:
        if previous.conversation_id != conversation.id or previous.author_id != actor or previous.body != text:
            raise HTTPException(409, 'El identificador de envío ya corresponde a otro mensaje.')
        return previous
    message = ChatMessage(conversation_id=conversation.id, direction='out', author_kind='agent',
        author_id=actor, body=text, status='queued', wa_request_id=request_id, created_at=now())
    try:
        async with session.begin_nested():
            session.add(message)
            await session.flush()
    except IntegrityError:
        previous = await session.scalar(select(ChatMessage).where(ChatMessage.wa_request_id == request_id))
        if (previous and previous.conversation_id == conversation.id
                and previous.author_id == actor and previous.body == text):
            return previous
        raise HTTPException(409, 'El identificador de envío ya corresponde a otro mensaje.') from None
    conversation.bot_active = False
    conversation.last_message_at = now()
    await session.flush()
    return message


async def tick(factory):
    # Exactly one worker per gateway. Database event commit precedes gateway acknowledgment.
    events = await gateway.call('/events')
    for event in events:
        try:
            async with factory() as session, session.begin():
                await ingest(session, event)
        except MirrorEventError as exc:
            # The failed transaction has rolled back. Move, never discard, the ORIGINAL encrypted
            # event in the gateway so that later events and outbound messages can make progress.
            # If preservation fails (or the gateway is an older version), stop without ACK.
            await gateway.call('/events/quarantine', {'sequence': event['seq'], 'reason': exc.code})
            logger.warning('WhatsApp event preserved for review (sequence=%d reason=%s)', event['seq'], exc.code)
            continue
        await gateway.call('/events/ack', {'sequences': [event['seq']]})
    async with factory() as session:
        ids = list((await session.scalars(select(ChatMessage.id).where(
            ChatMessage.wa_request_id.is_not(None), ChatMessage.status.in_(['queued', 'sending']))
            .order_by(ChatMessage.id).limit(25))).all())
    for message_id in ids:
        async with factory() as session, session.begin():
            message = await session.get(ChatMessage, message_id, with_for_update=True)
            if message.status not in ('queued', 'sending'):
                continue
            conversation = await session.get(ChatConversation, message.conversation_id)
            registry = await registry_for(session, conversation)
            owner = registry.advisor_id if registry else conversation.advisor_id
            # Reassignment before transmission cancels a not-yet-attempted queued send.
            if message.status == 'queued' and owner != message.author_id:
                message.status = 'blocked'
                message.error = 'El contacto cambió de asesor antes de enviarse.'
                continue
            message.status = 'sending'
            payload = {'request_id': message.wa_request_id, 'phone': conversation.phone, 'text': message.body}
        # Timeout: retain "sending" and query the SAME request id next tick, never a new send.
        result = await gateway.call('/send', payload)
        async with factory() as session, session.begin():
            message = await session.get(ChatMessage, message_id, with_for_update=True)
            if message.status in ('sent', 'delivered', 'read'):
                continue
            if result['state'] == 'offline':
                message.status = 'queued'
                break
            message.external_id = result.get('external_id')
            message.status = result['state'] if result['state'] in ('sent', 'unknown') else 'unknown'
            if message.status == 'sent':
                message.sent_at = parse_time(result['at'])
                message.error = None
            else:
                message.error = 'Envío sin confirmar. Comprueba WhatsApp antes de enviar otro mensaje.'
            await apply_receipt(session, message)
            await record_contact(session, message)
    async with factory() as session, session.begin():
        heartbeat = await session.get(MonitorState, 'whatsapp-worker')
        if heartbeat is None:
            heartbeat = MonitorState(account_id='whatsapp-worker')
            session.add(heartbeat)
        heartbeat.status = 'running'
        heartbeat.observed_at = now()
