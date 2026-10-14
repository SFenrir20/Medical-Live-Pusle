from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from ...shared.db import Base


class EventFact(Base):
    __tablename__ = 'event_facts'
    event_id = Column(String(128), ForeignKey('raw_events.event_id'), primary_key=True)
    broadcast_id = Column(Integer, ForeignKey('broadcasts.id'), nullable=False, index=True)
    account_id = Column(String(32), nullable=False)
    user_key = Column(String(128))
    kind = Column(String(32), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    comments = Column(Integer, nullable=False, default=0)
    likes = Column(Integer, nullable=False, default=0)
    shares = Column(Integer, nullable=False, default=0)
    gifts = Column(Integer, nullable=False, default=0)
    diamonds = Column(Integer, nullable=False, default=0)
    viewers = Column(Integer)
    interested = Column(Boolean, nullable=False, default=False)
    phones = Column(JSON, nullable=False, default=list)
    lead_id = Column(String(36), ForeignKey('leads.id'))


class Lead(Base):
    __tablename__ = 'leads'
    id = Column(String(36), primary_key=True)
    status = Column(String(24), nullable=False, default='new')
    review_needed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LeadAlias(Base):
    __tablename__ = 'lead_aliases'
    user_key = Column(String(128), primary_key=True)
    lead_id = Column(String(36), ForeignKey('leads.id'), nullable=False, index=True)
    username = Column(String(128))


class LeadPhone(Base):
    __tablename__ = 'lead_phones'
    phone = Column(String(20), primary_key=True)
    lead_id = Column(String(36), ForeignKey('leads.id'), nullable=False, index=True)


class LeadAudit(Base):
    __tablename__ = 'lead_audit'
    id = Column(String(36), primary_key=True)
    lead_id = Column(String(36), ForeignKey('leads.id'), nullable=False)
    actor = Column(String(255), nullable=False)
    action = Column(String(24), nullable=False)
    previous = Column(String(24))
    value = Column(String(24))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MonitorState(Base):
    __tablename__ = 'monitor_states'
    account_id = Column(String(32), primary_key=True)
    status = Column(String(24), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    offline_since = Column(DateTime(timezone=True))
    last_error = Column(String(120))


class UserRole(Base):
    __tablename__ = 'user_roles'
    user_id = Column(String(255), primary_key=True)
    role = Column(String(24), nullable=False)


class RoleAudit(Base):
    __tablename__ = 'role_audit'
    id = Column(String(36), primary_key=True)
    actor = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    role = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
