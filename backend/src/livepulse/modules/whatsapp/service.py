"""Real mirror transport, independent of simulator/bots. All sends pass through an outbox."""
import re
from datetime import datetime, timezone

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


def now():
    return datetime.now(timezone.utc)


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return result


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
    if await session.get(MirrorEvent, event['id']):
        return
    phone = event['phone']
    if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        raise ValueError('Invalid phone from mirror')
    at = parse_time(event['at'])
    external_id = event['external_id']
    if event['type'] == 'receipt':
        receipt = await session.get(MirrorReceipt, external_id)
        if receipt is None:
            receipt = MirrorReceipt(external_id=external_id, phone=phone)
            session.add(receipt)
        if receipt.phone != phone:
            raise ValueError('Receipt phone mismatch')
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
                raise ValueError('Outgoing conversation mismatch')
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
        raise ValueError('Unknown mirror event')
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
        async with factory() as session, session.begin():
            await ingest(session, event)
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
