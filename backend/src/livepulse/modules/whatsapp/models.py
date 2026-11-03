from sqlalchemy import Column, DateTime, String, func

from ...shared.db import Base


class MirrorEvent(Base):
    """Inbox deduplication. Commit this with the message, then acknowledge the gateway."""
    __tablename__ = 'wa_events'
    id = Column(String(36), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MirrorReceipt(Base):
    """Receipts may precede their message. Preserve them, including their clock source."""
    __tablename__ = 'wa_receipts'
    external_id = Column(String(128), primary_key=True)
    phone = Column(String(20), nullable=False)
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))
    delivered_clock = Column(String(16))
    read_clock = Column(String(16))
