"""Channel-agnostic chat core: channels, conversations and messages.

Nothing here knows WhatsApp. A channel is an adapter (see channels.py): today the simulator and
the WhatsApp mirror, later the official API. Flows, the AI agent and broadcasts (module
`automation`) only talk to this core."""
from sqlalchemy import (
    JSON,
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
    UniqueConstraint,
    func,
    text,
)

from ...shared.db import Base

PK_BIG = BigInteger().with_variant(Integer, 'sqlite')
CHANNEL_KINDS = ('simulator', 'whatsapp_mirror', 'whatsapp_cloud')


class ChatChannel(Base):
    __tablename__ = 'chat_channels'
    id = Column(String(32), primary_key=True)
    kind = Column(String(24), nullable=False)
    name = Column(String(100), nullable=False)
    status = Column(String(16), nullable=False, server_default='active')   # active | disabled
    # Overrides of the safe defaults for this kind of channel (see policy.py).
    policy = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("kind IN ('simulator','whatsapp_mirror','whatsapp_cloud')",
                        name='ck_chat_channels_kind'),
        CheckConstraint("status IN ('active','disabled')", name='ck_chat_channels_status'),
    )


class ChatConversation(Base):
    __tablename__ = 'chat_conversations'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    channel_id = Column(String(32), ForeignKey('chat_channels.id'), nullable=False)
    phone = Column(String(20), nullable=False)               # E.164
    contact_name = Column(String(128))
    registry_id = Column(PK_BIG)                             # phone_registry.id when it is known
    advisor_id = Column(String(64))
    tags = Column(JSON, nullable=False, default=list)
    # CRM: the stage lives on the contact when there is one; this is only for a WhatsApp-only number.
    stage = Column(String(10), nullable=False, server_default='new')
    result = Column(String(20))
    archived = Column(Boolean, nullable=False, server_default=text('false'))
    # The bot may answer only while this is true and now is past bot_paused_until. A person
    # writing in the conversation pauses it (human takeover).
    bot_active = Column(Boolean, nullable=False, server_default=text('true'))
    bot_paused_until = Column(DateTime(timezone=True))
    bot_replies = Column(Integer, nullable=False, server_default='0')   # AI answers in a row
    unread = Column(Integer, nullable=False, server_default='0')
    last_inbound_at = Column(DateTime(timezone=True))
    last_message_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('channel_id', 'phone', name='uq_chat_conversation_phone'),
        Index('ix_chat_conversations_last', 'last_message_at'),
    )


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    conversation_id = Column(PK_BIG, ForeignKey('chat_conversations.id'), nullable=False)
    direction = Column(String(3), nullable=False)             # in | out
    author_kind = Column(String(10), nullable=False)          # contact | agent | bot | system
    author_id = Column(String(255))
    body = Column(Text, nullable=False)
    status = Column(String(10), nullable=False)               # received | sent | failed | blocked
    error = Column(String(200))
    external_id = Column(String(128))                         # provider message id (idempotency)
    wa_request_id = Column(String(36), unique=True)
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))
    observed_at = Column(DateTime(timezone=True))
    flow_run_id = Column(PK_BIG)
    broadcast_id = Column(PK_BIG)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('conversation_id', 'external_id', name='uq_chat_message_external'),
        CheckConstraint("direction IN ('in','out')", name='ck_chat_messages_direction'),
        CheckConstraint("author_kind IN ('contact','agent','bot','system')",
                        name='ck_chat_messages_author'),
        Index('ix_chat_messages_conv', 'conversation_id', 'created_at'),
        Index('ix_chat_messages_author', 'author_kind', 'created_at'),
        Index('ix_chat_messages_sent', 'conversation_id', 'sent_at'),
    )


class OptOut(Base):
    """People who asked not to receive automatic or mass messages. Never written to again by
    a bot or a broadcast (a person can still answer if they write first)."""
    __tablename__ = 'chat_opt_outs'
    phone = Column(String(20), primary_key=True)
    reason = Column(String(200))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
