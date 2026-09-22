"""Idempotencia por Idempotency-Key para entrada/salida/relevo."""
from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..shared.db import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String(64), primary_key=True)
    scope = Column(String(32), nullable=False)  # check-in | check-out | handover
    response = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
