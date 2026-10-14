"""PostgresSink against real PostgreSQL, in a disposable schema."""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.broadcasts.sink import PostgresSink

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                                reason="Requires isolated test PostgreSQL")


@pytest.fixture
async def factory():
    url = os.environ["DATABASE_URL"]
    schema = "test_sink_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: RawEvent.metadata.create_all(
            sync, tables=[Broadcast.__table__, RawEvent.__table__]))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def event(event_id="medical:r1:comment:m1", account="medical"):
    return {"event_id": event_id, "account_id": account, "broadcast_id": None,
            "type": "comment", "payload": {"user": "ana"}, "raw_text": "hola"}


async def count(factory):
    async with factory() as session:
        return (await session.execute(select(func.count()).select_from(RawEvent))).scalar_one()


async def test_emit_persists_and_redelivery_is_noop(factory):
    sink = PostgresSink(factory)
    assert await sink.emit(event()) is True
    assert await sink.emit(event()) is False
    assert await count(factory) == 1


async def test_concurrent_duplicates_store_one_row(factory):
    sink = PostgresSink(factory)
    results = await asyncio.gather(*(sink.emit(event()) for _ in range(5)))
    assert results.count(True) == 1
    assert await count(factory) == 1


async def test_accounts_are_kept_apart(factory):
    sink = PostgresSink(factory)
    await sink.emit(event("medical:r1:comment:m1", "medical"))
    await sink.emit(event("medical-2:r1:comment:m1", "medical-2"))
    assert await count(factory) == 2
