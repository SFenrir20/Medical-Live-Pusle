"""Sends the messages agents scheduled. Runs in the WhatsApp worker (the one process that owns the
outbox), so a scheduled message becomes a normal queued message and gets the same statuses,
receipts and idempotency as one written by hand."""
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from ..chat.models import ChatConversation
from ..chat.service import utcnow
from ..whatsapp import service as whatsapp
from .models import ChatScheduled

log = logging.getLogger(__name__)


async def tick(factory, now: datetime | None = None) -> int:
    now = now or utcnow()
    queued = 0
    async with factory() as session, session.begin():
        due = (await session.scalars(select(ChatScheduled).where(
            ChatScheduled.status == 'pending', ChatScheduled.send_at <= now)
            .order_by(ChatScheduled.send_at).limit(25).with_for_update(skip_locked=True))).all()
        for item in due:
            conversation = await session.get(ChatConversation, item.conversation_id)
            registry = await whatsapp.registry_for(session, conversation, lock=True)
            owner = registry.advisor_id if registry else conversation.advisor_id
            if owner != item.author_id:
                # She no longer owns the contact: nothing leaves under her name.
                item.status, item.detail = 'cancelled', 'El contacto cambió de asesor antes del envío.'
                continue
            message = await whatsapp.queue_message(session, conversation, item.author_id,
                                                   str(uuid4()), item.body)
            item.status, item.message_id = 'queued', message.id
            queued += 1
    return queued
