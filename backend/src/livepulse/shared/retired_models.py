"""Retired attendance schema, imported ONLY by Alembic.

Keep existing tables and migration history intact without exposing attendance in the app.
Do not import this module from runtime services.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, func, text

from .db import Base


class ArchivedShift(Base):
    __tablename__ = "shifts"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(32), nullable=False)
    user_id = Column(String(255), nullable=False)
    display_name = Column(String(100))
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    end_reason = Column(String(16))
    closed_by = Column(String(255))

    __table_args__ = (
        Index("uq_active_shift_per_account", "account_id", unique=True,
              postgresql_where=text("ended_at IS NULL")),
        Index("ix_shifts_user_started", "user_id", "started_at", "id"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_shift_time"),
        CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL AND closed_by IS NULL) OR "
            "(ended_at IS NOT NULL AND end_reason IS NOT NULL "
            "AND end_reason IN ('manual', 'handover') AND closed_by IS NOT NULL)",
            name="ck_shift_closure"),
    )


class ArchivedIdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String(64), primary_key=True)
    scope = Column(String(32), nullable=False)  # check-in | check-out | handover
    response = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
