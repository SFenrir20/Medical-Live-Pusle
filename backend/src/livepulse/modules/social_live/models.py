"""Social Live integration schema.

Permanent: tiktok_accounts, tiktokers, lives, live_metrics, captured_phones.
Temporary (purged after COMMENTS_RETENTION_DAYS): live_comments, live_event_keys.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
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
LIVE_STATUSES = ('scheduled', 'live', 'finished', 'cancelled')
PHONE_SOURCES = ('comment', 'manual_capture', 'direct_message', 'speech', 'other')
PHONE_STATUSES = ('new', 'contacted', 'qualified', 'discarded')


class TiktokAccount(Base):
    __tablename__ = 'tiktok_accounts'
    id = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    username = Column(String(64), nullable=False, unique=True)
    type = Column(String(32), nullable=False, server_default='live')
    active = Column(Boolean, nullable=False, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Tiktoker(Base):
    __tablename__ = 'tiktokers'
    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    active = Column(Boolean, nullable=False, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Live(Base):
    __tablename__ = 'lives'
    id = Column(String(40), primary_key=True)
    tiktoker_id = Column(String(64), ForeignKey('tiktokers.id'), nullable=False)
    account_id = Column(String(32), ForeignKey('tiktok_accounts.id'), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    status = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('scheduled','live','finished','cancelled')", name='ck_lives_status'),
        CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='ck_lives_time'),
        Index('ix_lives_started', 'started_at'),
        Index('ix_lives_tiktoker', 'tiktoker_id', 'started_at'),
        Index('ix_lives_account', 'account_id', 'started_at'),
    )


class LiveComment(Base):
    """Temporary detail. Deleted by the retention job; aggregates live in live_metrics."""
    __tablename__ = 'live_comments'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    live_id = Column(String(40), ForeignKey('lives.id'), nullable=False)
    username = Column(String(128), nullable=False)
    comment = Column(Text, nullable=False)
    phone_detected = Column(String(20))
    interested = Column(Boolean, nullable=False, server_default=text('false'))
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index('ix_live_comments_live_created', 'live_id', 'created_at'),
        Index('ix_live_comments_live_username', 'live_id', 'username'),
        Index('ix_live_comments_created', 'created_at'),
    )


class LiveEventKey(Base):
    """Idempotency of client retries (so a resent like is not counted twice). Temporary."""
    __tablename__ = 'live_event_keys'
    live_id = Column(String(40), ForeignKey('lives.id'), primary_key=True)
    event_id = Column(String(128), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index('ix_live_event_keys_created', 'created_at'),)


class LiveMetrics(Base):
    """Permanent consolidated metrics; never removed by comment retention."""
    __tablename__ = 'live_metrics'
    id = Column(Integer, primary_key=True, autoincrement=True)
    live_id = Column(String(40), ForeignKey('lives.id'), nullable=False, unique=True)
    views = Column(Integer, nullable=False, server_default='0')
    unique_viewers = Column(Integer, nullable=False, server_default='0')
    comments_count = Column(Integer, nullable=False, server_default='0')
    likes_count = Column(Integer, nullable=False, server_default='0')
    shares_count = Column(Integer, nullable=False, server_default='0')
    new_followers = Column(Integer, nullable=False, server_default='0')
    donations_count = Column(Integer, nullable=False, server_default='0')
    direct_messages_count = Column(Integer, nullable=False, server_default='0')
    interested_viewers = Column(Integer, nullable=False, server_default='0')
    phones_captured = Column(Integer, nullable=False, server_default='0')
    leads_per_hour = Column(Float, nullable=False, server_default='0')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CapturedPhone(Base):
    __tablename__ = 'captured_phones'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    live_id = Column(String(40), ForeignKey('lives.id'), nullable=False)
    phone = Column(String(20), nullable=False)
    tiktok_username = Column(String(128))
    source = Column(String(24), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    contacted_at = Column(DateTime(timezone=True))
    advisor_id = Column(String(64))
    status = Column(String(16), nullable=False, server_default='new')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('live_id', 'phone', name='uq_captured_phone_live'),
        CheckConstraint("status IN ('new','contacted','qualified','discarded')",
                        name='ck_captured_phones_status'),
        CheckConstraint("source IN ('comment','manual_capture','direct_message','speech','other')",
                        name='ck_captured_phones_source'),
        CheckConstraint('contacted_at IS NULL OR contacted_at >= captured_at',
                        name='ck_captured_phones_contact_time'),
        Index('ix_captured_phones_captured', 'captured_at'),
        Index('ix_captured_phones_status', 'status', 'captured_at'),
    )
