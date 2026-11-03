"""Automation tables: flows (diagrams), AI agent, broadcasts, and the audit of admin actions."""
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


class Flow(Base):
    """A diagram: nodes and edges stored as JSON (see graph.py). Created disabled."""
    __tablename__ = 'automation_flows'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(String(300))
    channel_id = Column(String(32), ForeignKey('chat_channels.id'), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default=text('false'))
    graph = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, server_default='1')
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FlowRun(Base):
    __tablename__ = 'automation_runs'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    flow_id = Column(PK_BIG, ForeignKey('automation_flows.id'), nullable=False)
    conversation_id = Column(PK_BIG, ForeignKey('chat_conversations.id'), nullable=False)
    status = Column(String(10), nullable=False)      # running | waiting | done | stopped | failed
    current_node = Column(String(24))
    resume_at = Column(DateTime(timezone=True))
    context = Column(JSON, nullable=False, default=dict)
    steps_count = Column(Integer, nullable=False, server_default='0')
    test = Column(Boolean, nullable=False, server_default=text('false'))
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    reason = Column(String(300))

    __table_args__ = (
        CheckConstraint("status IN ('running','waiting','done','stopped','failed')",
                        name='ck_automation_runs_status'),
        Index('ix_automation_runs_due', 'status', 'resume_at'),
        Index('ix_automation_runs_flow', 'flow_id', 'started_at'),
    )


class FlowStep(Base):
    __tablename__ = 'automation_steps'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    run_id = Column(PK_BIG, ForeignKey('automation_runs.id'), nullable=False)
    node_id = Column(String(24), nullable=False)
    node_type = Column(String(32), nullable=False)
    outcome = Column(String(300), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index('ix_automation_steps_run', 'run_id', 'id'),)


class AiAgent(Base):
    """The one AI agent of the clinic (row id 1). The provider key is stored encrypted and is
    never sent back to the browser."""
    __tablename__ = 'ai_agent'
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, server_default=text('false'))
    provider = Column(String(20), nullable=False, server_default='echo')
    model = Column(String(80), nullable=False, server_default='')
    base_url = Column(String(200), nullable=False, server_default='')
    api_key_encrypted = Column(Text)
    name = Column(String(60), nullable=False, server_default='Asistente virtual')
    clinic_name = Column(String(80), nullable=False, server_default='la clínica')
    instructions = Column(Text, nullable=False, server_default='')
    knowledge_only = Column(Boolean, nullable=False, server_default=text('true'))
    handoff_keywords = Column(JSON, nullable=False, default=list)
    handoff_message = Column(String(300), nullable=False, server_default='')
    max_replies = Column(Integer, nullable=False, server_default='6')
    daily_message_cap = Column(Integer, nullable=False, server_default='200')
    updated_by = Column(String(255))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AiKnowledgeDoc(Base):
    __tablename__ = 'ai_knowledge_docs'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    title = Column(String(120), nullable=False)
    body = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AiUsage(Base):
    __tablename__ = 'ai_usage'
    day = Column(String(10), primary_key=True)        # YYYY-MM-DD (UTC)
    messages = Column(Integer, nullable=False, server_default='0')
    input_tokens = Column(Integer, nullable=False, server_default='0')
    output_tokens = Column(Integer, nullable=False, server_default='0')


class Broadcast(Base):
    __tablename__ = 'automation_broadcasts'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    channel_id = Column(String(32), ForeignKey('chat_channels.id'), nullable=False)
    body = Column(Text, nullable=False)
    audience = Column(JSON, nullable=False, default=dict)
    status = Column(String(10), nullable=False, server_default='draft')
    scheduled_at = Column(DateTime(timezone=True))
    pause_reason = Column(String(200))
    total = Column(Integer, nullable=False, server_default='0')
    sent = Column(Integer, nullable=False, server_default='0')
    failed = Column(Integer, nullable=False, server_default='0')
    skipped = Column(Integer, nullable=False, server_default='0')
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('draft','scheduled','sending','paused','done','cancelled')",
                        name='ck_automation_broadcasts_status'),
    )


class BroadcastRecipient(Base):
    __tablename__ = 'automation_broadcast_recipients'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    broadcast_id = Column(PK_BIG, ForeignKey('automation_broadcasts.id'), nullable=False)
    phone = Column(String(20), nullable=False)
    name = Column(String(128))
    status = Column(String(8), nullable=False, server_default='pending')
    error = Column(String(200))
    sent_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint('broadcast_id', 'phone', name='uq_broadcast_recipient'),
        CheckConstraint("status IN ('pending','sent','failed','skipped')",
                        name='ck_broadcast_recipients_status'),
        Index('ix_broadcast_recipients_pending', 'broadcast_id', 'status'),
    )


class AutomationAudit(Base):
    """Who changed what in the automation tools (enabling a flow, starting a broadcast, editing
    the policy of a channel, setting the AI key). Append-only."""
    __tablename__ = 'automation_audit'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    actor = Column(String(255), nullable=False)
    action = Column(String(40), nullable=False)
    entity = Column(String(30), nullable=False)
    entity_id = Column(String(40))
    detail = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index('ix_automation_audit_created', 'created_at'),)
