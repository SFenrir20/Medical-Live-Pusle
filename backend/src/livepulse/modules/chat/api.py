"""Conversations and the simulator console. Only people with `automation:manage` (admin) can read
or write conversations through this API for now: the agents' own chat inbox arrives with the
WhatsApp mirror, and managers see counts, never messages."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...shared.db import get_session
from ..social_live import queries
from ..social_live.security import require_scope
from . import service
from .models import ChatChannel, ChatConversation, ChatMessage
from .policy import PolicyViolation

router = APIRouter(prefix='/api/chat', tags=['chat'])
admin = require_scope('automation:manage')


def message_item(m: ChatMessage) -> dict:
    return {'id': m.id, 'direction': m.direction, 'author_kind': m.author_kind,
            'author_id': m.author_id, 'body': m.body, 'status': m.status, 'error': m.error,
            'flow_run_id': m.flow_run_id, 'broadcast_id': m.broadcast_id,
            'at': queries.iso(service.aware(m.created_at))}


def conversation_item(c: ChatConversation, last: ChatMessage | None = None) -> dict:
    return {'id': c.id, 'channel_id': c.channel_id, 'phone': c.phone, 'name': c.contact_name,
            'tags': c.tags or [], 'bot_active': c.bot_active,
            'bot_paused_until': queries.iso(service.aware(c.bot_paused_until)),
            'advisor_id': c.advisor_id, 'unread': c.unread,
            'last_message_at': queries.iso(service.aware(c.last_message_at)),
            'last': message_item(last) if last else None}


class InboundIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)
    text: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=100)


@router.post('/simulator/inbound')
async def simulator_inbound(body: InboundIn, who=Depends(admin), session=Depends(get_session)):
    """A pretend patient writes on the simulator channel. Any enabled flow of that channel
    reacts exactly as it would on a real one."""
    await service.ensure_simulator(session)
    try:
        conversation, message = await service.receive_message(
            session, service.SIMULATOR_ID, body.phone, body.text, name=body.name)
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    await session.commit()
    rows = (await session.scalars(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.id))).all()
    return {'conversation': conversation_item(conversation),
            'messages': [message_item(m) for m in rows]}


@router.get('/conversations')
async def conversations(channel_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                        who=Depends(admin), session=Depends(get_session)):
    query = select(ChatConversation).order_by(ChatConversation.last_message_at.desc().nullslast(),
                                              ChatConversation.id.desc()).limit(limit)
    if channel_id:
        query = query.where(ChatConversation.channel_id == channel_id)
    rows = (await session.scalars(query)).all()
    last_ids = dict((await session.execute(
        select(ChatMessage.conversation_id, func.max(ChatMessage.id)).where(
            ChatMessage.conversation_id.in_([c.id for c in rows]))
        .group_by(ChatMessage.conversation_id))).all()) if rows else {}
    last = {m.id: m for m in (await session.scalars(select(ChatMessage).where(
        ChatMessage.id.in_(list(last_ids.values()))))).all()} if last_ids else {}
    return {'items': [conversation_item(c, last.get(last_ids.get(c.id))) for c in rows]}


async def _conversation(session, conversation_id: int) -> ChatConversation:
    row = await session.get(ChatConversation, conversation_id)
    if row is None:
        raise HTTPException(404, 'Conversación no encontrada.')
    return row


@router.get('/conversations/{conversation_id}/messages')
async def messages(conversation_id: int, who=Depends(admin), session=Depends(get_session)):
    conversation = await _conversation(session, conversation_id)
    rows = (await session.scalars(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id))).all()
    return {'conversation': conversation_item(conversation),
            'messages': [message_item(m) for m in rows]}


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post('/conversations/{conversation_id}/messages')
async def send(conversation_id: int, body: SendIn, who=Depends(admin),
               session=Depends(get_session)):
    """A person writes in the conversation: the bot stays quiet there for a while."""
    conversation = await _conversation(session, conversation_id)
    try:
        message = await service.send_message(session, conversation, body.text,
                                             author_kind='agent', author_id=who['user_id'])
    except PolicyViolation as problem:
        await session.commit()
        raise HTTPException(409, problem.message) from None
    await session.commit()
    return message_item(message)


class ConversationPatch(BaseModel):
    bot_active: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


@router.patch('/conversations/{conversation_id}')
async def patch(conversation_id: int, body: ConversationPatch, who=Depends(admin),
                session=Depends(get_session)):
    conversation = await _conversation(session, conversation_id)
    if body.bot_active is not None:
        conversation.bot_active = body.bot_active
        if body.bot_active:
            conversation.bot_paused_until = None
    if body.tags is not None:
        conversation.tags = sorted({t.strip()[:30] for t in body.tags if t.strip()})
    await session.commit()
    return conversation_item(conversation)


@router.get('/channels/{channel_id}')
async def channel(channel_id: str, who=Depends(admin), session=Depends(get_session)):
    row = await session.get(ChatChannel, channel_id)
    if row is None:
        raise HTTPException(404, 'Canal no encontrado.')
    return {'id': row.id, 'kind': row.kind, 'name': row.name, 'status': row.status}
