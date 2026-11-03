"""Receive and send messages through the channel adapters, enforcing the channel policy.

Every automatic reply (flow, AI agent, broadcast) goes through `send_message`, so the limits,
the opt-out list and the human-takeover rule apply to all of them in one place."""
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...shared.config import settings
from . import hooks
from .channels import ChannelUnavailable, adapter_for
from .models import ChatChannel, ChatConversation, ChatMessage, OptOut
from .policy import PolicyViolation, check_outbound

log = logging.getLogger(__name__)
SIMULATOR_ID = 'simulador'
OPT_OUT_EXACT = {'baja', 'stop', 'no mas', 'cancelar', 'no gracias', 'darme de baja'}
OPT_OUT_CONTAINS = ('no quiero recibir', 'dejen de escribir', 'no me escriban', 'no me escribas',
                    'darme de baja', 'quitenme de la lista')


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def plain(text: str) -> str:
    """Lower case, no accents, single spaces, no punctuation at the ends."""
    folded = unicodedata.normalize('NFKD', text.lower())
    folded = ''.join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', folded).strip(' .,;:!¡?¿"\'')


def wants_opt_out(text: str) -> bool:
    cleaned = plain(text)
    return cleaned in OPT_OUT_EXACT or any(term in cleaned for term in OPT_OUT_CONTAINS)


def normalize(phone: str) -> str:
    from ..social_live.service import normalize_phone
    found = normalize_phone(phone)
    if found:
        return found
    digits = re.sub(r'\D', '', phone)
    if not 8 <= len(digits) <= 15:
        raise ValueError('Teléfono inválido.')
    return '+' + digits


async def ensure_simulator(session) -> ChatChannel:
    channel = await session.get(ChatChannel, SIMULATOR_ID)
    if channel is None:
        channel = ChatChannel(id=SIMULATOR_ID, kind='simulator', name='Simulador (pruebas)',
                              policy={})
        session.add(channel)
        await session.flush()
    return channel


async def get_conversation(session, channel_id: str, phone: str, name: str | None = None,
                           create: bool = True) -> ChatConversation | None:
    row = await session.scalar(select(ChatConversation).where(
        ChatConversation.channel_id == channel_id, ChatConversation.phone == phone))
    if row is not None or not create:
        if row is not None and name and not row.contact_name:
            row.contact_name = name[:128]
        return row
    registry_id, known_name = None, None
    from ..social_live.models import PhoneRegistry
    contact = await session.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == phone))
    if contact is not None:
        registry_id = contact.id
        known_name = (contact.first_username or '').lstrip('@') or None
    row = ChatConversation(channel_id=channel_id, phone=phone, tags=[],
                           contact_name=(name or known_name or None) and (name or known_name)[:128],
                           registry_id=registry_id, created_at=utcnow())
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:  # created at the same time by another request
        row = await session.scalar(select(ChatConversation).where(
            ChatConversation.channel_id == channel_id, ChatConversation.phone == phone))
    return row


async def receive_message(session, channel_id: str, phone: str, text: str, *,
                          external_id: str | None = None, name: str | None = None,
                          at: datetime | None = None):
    """A message written BY the person. Idempotent by external id. Returns (conversation,
    message) or (conversation, None) for a duplicate. Opt-out words are recorded, and then the
    registered handlers (the automation engine) run."""
    phone = normalize(phone)
    at = at or utcnow()
    conversation = await get_conversation(session, channel_id, phone, name)
    if external_id is not None:
        seen = await session.scalar(select(ChatMessage.id).where(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.external_id == external_id))
        if seen:
            return conversation, None
    message = ChatMessage(conversation_id=conversation.id, direction='in',
                          author_kind='contact', body=text[:4000], status='received',
                          external_id=external_id, created_at=at)
    session.add(message)
    conversation.last_inbound_at = at
    conversation.last_message_at = at
    conversation.unread = (conversation.unread or 0) + 1
    conversation.bot_replies = 0 if conversation.bot_replies is None else conversation.bot_replies
    if wants_opt_out(text) and await session.get(OptOut, phone) is None:
        session.add(OptOut(phone=phone, reason=text[:200]))
    await session.flush()
    await hooks.run_inbound(session, conversation, message)
    return conversation, message


async def send_message(session, conversation: ChatConversation, text: str, *, author_kind: str,
                       author_id: str | None = None, flow_run_id: int | None = None,
                       broadcast_id: int | None = None, now: datetime | None = None
                       ) -> ChatMessage:
    """Send through the channel adapter. Raises PolicyViolation when the policy blocks it (the
    blocked attempt is stored for the record). Humans pause the bot on this conversation."""
    now = now or utcnow()
    channel = await session.get(ChatChannel, conversation.channel_id)
    text = text.strip()[:4000]
    try:
        await check_outbound(session, channel, conversation, author_kind, now,
                             broadcast=broadcast_id is not None)
        result = await adapter_for(channel.kind).send(conversation.phone, text)
    except (PolicyViolation, ChannelUnavailable) as problem:
        if isinstance(problem, ChannelUnavailable):
            problem = PolicyViolation('channel_unavailable', str(problem), retry=True)
        if not problem.retry:  # rate limits are transient: do not fill the log with them
            session.add(ChatMessage(conversation_id=conversation.id, direction='out',
                                    author_kind=author_kind, author_id=author_id, body=text,
                                    status='blocked', error=problem.code[:200],
                                    flow_run_id=flow_run_id, broadcast_id=broadcast_id,
                                    created_at=now))
            await session.flush()
        raise problem
    message = ChatMessage(conversation_id=conversation.id, direction='out',
                          author_kind=author_kind, author_id=author_id, body=text,
                          status='sent', external_id=result.external_id,
                          flow_run_id=flow_run_id, broadcast_id=broadcast_id, created_at=now)
    session.add(message)
    conversation.last_message_at = now
    if author_kind == 'agent':
        # Human takeover: the bot stays quiet here for a while, and its streak restarts.
        conversation.bot_paused_until = now + timedelta(hours=settings.bot_pause_hours)
        conversation.bot_replies = 0
    await session.flush()
    return message


def bot_may_answer(conversation: ChatConversation, now: datetime) -> bool:
    if not conversation.bot_active:
        return False
    paused = aware(conversation.bot_paused_until)
    return paused is None or paused <= now
