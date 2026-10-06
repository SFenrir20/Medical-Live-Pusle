from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, text

from ...shared.db import Base


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(32), nullable=False)
    user_id = Column(String(255), nullable=False)
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
