"""Sesiones LIVE y eventos crudos por cuenta.

Reglas:
- Todo evento trae account_id (medical | medical-2) y event_id global unico.
- Reprocesar el mismo event_id es no-op (UNIQUE).
- Desconexion != fin confirmado: solo LiveEnd + gracia/re-chequeo cierra.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.db import Base


class Broadcast(Base):
    __tablename__ = "broadcasts"
    __table_args__ = (UniqueConstraint("account_id", "room_id", name="uq_broadcast_room"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tiktok_username: Mapped[str] = mapped_column(String(64), nullable=False)
    room_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True solo tras LiveEnd + gracia/re-chequeo. Un corte de red no lo marca.
    end_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RawEvent(Base):
    __tablename__ = "raw_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False)
    broadcast_id: Mapped[int | None] = mapped_column(ForeignKey("broadcasts.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # comment|gift|like|share|join|live_end
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_raw_events_account_occurred", "account_id", "occurred_at"),)
