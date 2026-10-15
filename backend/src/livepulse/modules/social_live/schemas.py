"""Validated request bodies for the ingestion API."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

LIMA = ZoneInfo('America/Lima')
EventType = Literal['comment', 'like', 'view', 'viewer', 'interested', 'follow', 'donation',
                    'share', 'direct_message', 'phone_detected', 'phone_manual']
PhoneSource = Literal['comment', 'manual_capture', 'direct_message', 'speech', 'other']
PhoneStatus = Literal['new', 'contacted', 'qualified', 'discarded']


def aware(value: datetime | None) -> datetime | None:
    """Naive timestamps (no offset) are America/Lima wall-clock time, as the app shows them."""
    if value is None:
        return None
    value = value.replace(tzinfo=LIMA) if value.tzinfo is None else value
    return value.astimezone(timezone.utc)


class Stamped(BaseModel):
    @field_validator('timestamp', 'captured_at', 'started_at', 'ended_at', 'contacted_at',
                     check_fields=False, mode='after')
    @classmethod
    def normalize(cls, value):
        value = aware(value)
        if value is not None and value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('La fecha no puede estar en el futuro.')
        return value


class AccountIn(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=64)
    type: str = Field(default='live', min_length=1, max_length=32)
    active: bool = True

    @field_validator('username')
    @classmethod
    def strip_at(cls, value):
        return value.strip().lstrip('@')


class TiktokerIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_.:-]+$')
    name: str = Field(min_length=1, max_length=100)
    active: bool = True


class LiveIn(Stamped):
    live_id: str | None = Field(default=None, min_length=1, max_length=40,
                                pattern=r'^[A-Za-z0-9_-]+$')
    tiktoker_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=32)
    started_at: datetime | None = None
    status: Literal['scheduled', 'live'] = 'live'


class EventIn(Stamped):
    event_type: EventType
    username: str | None = Field(default=None, max_length=128)
    text: str | None = Field(default=None, max_length=2000)
    value: int = Field(default=1, ge=0, le=2_000_000_000)
    phone: str | None = Field(default=None, max_length=40)
    timestamp: datetime | None = None
    event_id: str | None = Field(default=None, min_length=1, max_length=128)


class EventBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class CommentIn(Stamped):
    username: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    timestamp: datetime | None = None
    event_id: str | None = Field(default=None, min_length=1, max_length=128)


class PhoneIn(Stamped):
    phone: str = Field(min_length=6, max_length=40)
    tiktok_username: str | None = Field(default=None, max_length=128)
    source: PhoneSource = 'manual_capture'
    captured_at: datetime | None = None


class PhoneUpdate(Stamped):
    status: PhoneStatus | None = None
    advisor_id: str | None = Field(default=None, min_length=1, max_length=64)
    contacted_at: datetime | None = None


class FinishIn(Stamped):
    ended_at: datetime | None = None
    status: Literal['finished', 'cancelled'] = 'finished'
