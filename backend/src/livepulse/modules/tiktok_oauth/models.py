from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.db import Base


class OAuthAttempt(Base):
    __tablename__ = "tiktok_oauth_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(128))
    app_id: Mapped[str] = mapped_column(String(100))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthConnection(Base):
    __tablename__ = "tiktok_oauth_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(100))
    authorized_by: Mapped[str] = mapped_column(String(128))
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    token_encrypted: Mapped[str] = mapped_column(Text)
    advertiser_ids: Mapped[list] = mapped_column(JSON)
    scopes: Mapped[list] = mapped_column(JSON)
