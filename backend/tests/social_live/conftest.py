"""Shared fixtures for Social Live tests (portable SQL on in-memory SQLite)."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from livepulse.entrypoints.api import app
from livepulse.modules.analytics.models import MonitorState, UserRole
from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.social_live import models as m
from livepulse.shared.config import settings
from livepulse.shared.db import get_session

TABLES = [m.TiktokAccount.__table__, m.Tiktoker.__table__, m.Live.__table__,
          m.LiveComment.__table__, m.LiveEventKey.__table__, m.LiveInterestedUser.__table__, m.LiveMetrics.__table__,
          m.CapturedPhone.__table__, m.PhoneRegistry.__table__,
          UserRole.__table__, Broadcast.__table__, RawEvent.__table__,
          m.ContactAudit.__table__, MonitorState.__table__]


@pytest.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, 'social_live_token', 'ingest-secret')
    monkeypatch.setattr(settings, 'medical360_token', 'read-secret')
    monkeypatch.setattr(settings, 'medical360_export_token', 'export-secret')
    monkeypatch.setattr(settings, 'comments_retention_days', 30)
    engine = create_async_engine('sqlite+aiosqlite://', poolclass=StaticPool,
                                 connect_args={'check_same_thread': False})
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: m.Live.metadata.create_all(sync, tables=TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        async with factory() as value:
            yield value

    app.dependency_overrides[get_session] = session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


