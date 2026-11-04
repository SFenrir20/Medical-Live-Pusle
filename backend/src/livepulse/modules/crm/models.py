"""CRM layer over the chat conversations: notes, scheduled messages, consent and quick replies.

The stage of a contact is NOT stored here: when the number is a LIVE contact its stage is the
contact's own status (new, contacted, qualified, discarded) so there is one truth for the whole
app; only a WhatsApp-only number keeps its stage on the conversation."""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)

from ...shared.db import Base

PK_BIG = BigInteger().with_variant(Integer, 'sqlite')


class ChatNote(Base):
    """Internal note about a conversation. The person never sees it."""
    __tablename__ = 'chat_notes'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    conversation_id = Column(PK_BIG, ForeignKey('chat_conversations.id'), nullable=False)
    author_id = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index('ix_chat_notes_conv', 'conversation_id', 'created_at'),)


class ChatScheduled(Base):
    """A message an agent asked to send later. At the time it goes through the same outbox as
    a message written now, and only if the agent still owns the contact."""
    __tablename__ = 'chat_scheduled'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    conversation_id = Column(PK_BIG, ForeignKey('chat_conversations.id'), nullable=False)
    author_id = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    send_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(10), nullable=False, server_default='pending')
    detail = Column(String(200))
    message_id = Column(PK_BIG)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('pending','queued','cancelled')", name='ck_chat_scheduled_status'),
        Index('ix_chat_scheduled_due', 'status', 'send_at'),
    )


class ChatConsent(Base):
    """Whether the person agreed to receive WhatsApp messages (by phone, not by channel). It
    gates campaigns; a person's own conversation with an agent does not need it."""
    __tablename__ = 'chat_consents'
    phone = Column(String(20), primary_key=True)
    status = Column(String(10), nullable=False)          # granted | revoked
    note = Column(String(200))
    changed_by = Column(String(255), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('granted','revoked')", name='ck_chat_consents_status'),
    )


class QuickReply(Base):
    """Pre-written answers ("mensajes pregrabados") that agents insert with a shortcut."""
    __tablename__ = 'chat_quick_replies'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    title = Column(String(80), nullable=False)
    shortcut = Column(String(30), nullable=False, unique=True)
    body = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, server_default=text('true'))
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
