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
    # Optional: who worked is derived from shifts by time (see queries.attribution).
    tiktoker_id = Column(String(64), ForeignKey('tiktokers.id'))
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


class LiveInterestedUser(Base):
    """Permanent deduplication, independent of temporary comment detail."""
    __tablename__ = 'live_interested_users'
    live_id = Column(String(40), ForeignKey('lives.id'), primary_key=True)
    username = Column(String(128), primary_key=True)


class LiveMetrics(Base):
    """Permanent consolidated metrics; never removed by comment retention.

    Audience: `peak_viewers` is the highest CONCURRENT audience sample and the average is
    viewer_sum / viewer_samples. They are not unique viewers; `unique_viewers` stays NULL
    ("not available") unless a source explicitly reports it."""
    __tablename__ = 'live_metrics'
    id = Column(Integer, primary_key=True, autoincrement=True)
    live_id = Column(String(40), ForeignKey('lives.id'), nullable=False, unique=True)
    views = Column(Integer, nullable=False, server_default='0')
    unique_viewers = Column(Integer)
    peak_viewers = Column(Integer, nullable=False, server_default='0')
    viewer_samples = Column(Integer, nullable=False, server_default='0')
    viewer_sum = Column(BigInteger, nullable=False, server_default='0')
    comments_count = Column(Integer, nullable=False, server_default='0')
    likes_count = Column(Integer, nullable=False, server_default='0')
    shares_count = Column(Integer, nullable=False, server_default='0')
    new_followers = Column(Integer, nullable=False, server_default='0')
    donations_count = Column(Integer, nullable=False, server_default='0')
    # Reported by whatever sends events. It is NOT evidence that private messages are captured.
    direct_messages_count = Column(Integer, nullable=False, server_default='0')
    interested_viewers = Column(Integer, nullable=False, server_default='0')
    # New numbers (first time ever seen) vs. every appearance in this live.
    phones_captured = Column(Integer, nullable=False, server_default='0')
    phone_mentions = Column(Integer, nullable=False, server_default='0')
    leads_per_hour = Column(Float, nullable=False, server_default='0')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PhoneRegistry(Base):
    """The unique contact (E.164). Created at its FIRST capture, anywhere, on any account.

    Later appearances live in captured_phones. Attention state (advisor, status, first contact
    time) is kept here, once per person, whatever the number of broadcasts it appeared in."""
    __tablename__ = 'phone_registry'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    phone = Column(String(20), nullable=False, unique=True)
    first_live_id = Column(String(40), ForeignKey('lives.id'))
    first_account_id = Column(String(32))
    first_captured_at = Column(DateTime(timezone=True), nullable=False)
    first_username = Column(String(128))
    first_source = Column(String(24), nullable=False, server_default='comment')
    status = Column(String(16), nullable=False, server_default='new')
    advisor_id = Column(String(64))
    assigned_at = Column(DateTime(timezone=True))
    contacted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('new','contacted','qualified','discarded')",
                        name='ck_phone_registry_status'),
        CheckConstraint('contacted_at IS NULL OR contacted_at >= first_captured_at',
                        name='ck_phone_registry_contact_time'),
        Index('ix_phone_registry_captured', 'first_captured_at'),
        Index('ix_phone_registry_advisor', 'advisor_id', 'status'),
    )


class CapturedPhone(Base):
    """One appearance of a number in a live (comment, manual capture...). is_new marks the
    appearance that was the first capture of that number."""
    __tablename__ = 'captured_phones'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    live_id = Column(String(40), ForeignKey('lives.id'), nullable=False)
    phone = Column(String(20), ForeignKey('phone_registry.phone'), nullable=False)
    tiktok_username = Column(String(128))
    source = Column(String(24), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    is_new = Column(Boolean, nullable=False, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('live_id', 'phone', name='uq_captured_phone_live'),
        CheckConstraint("source IN ('comment','manual_capture','direct_message','speech','other')",
                        name='ck_captured_phones_source'),
        Index('ix_captured_phones_captured', 'captured_at'),
        Index('ix_captured_phones_phone', 'phone'),
    )


class ContactAudit(Base):
    """Who did what to a contact, and when. Append-only."""
    __tablename__ = 'contact_audit'
    id = Column(PK_BIG, primary_key=True, autoincrement=True)
    registry_id = Column(PK_BIG, ForeignKey('phone_registry.id'), nullable=False)
    actor = Column(String(255), nullable=False)
    action = Column(String(24), nullable=False)
    previous = Column(String(64))
    value = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index('ix_contact_audit_registry', 'registry_id', 'created_at'),)
