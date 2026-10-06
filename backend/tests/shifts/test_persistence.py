"""API + real PostgreSQL tests. Each test owns a disposable, isolated schema."""
import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from livepulse.entrypoints.api import app
from livepulse.modules.shifts.models import Shift
from livepulse.shared.auth import get_current_user
from livepulse.shared.db import get_session
from livepulse.shared.idempotency import IdempotencyKey

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                                reason="Requires isolated test PostgreSQL")


@pytest.fixture
async def api():
    url = os.environ["DATABASE_URL"]
    schema = "test_shifts_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Shift.metadata.create_all(
            sync, tables=[Shift.__table__, IdempotencyKey.__table__]))

    async def session():
        async with factory() as value:
            yield value

    def user(x_test_user: str = Header(default="ana")):
        return {"id": x_test_user, "accounts": [] if x_test_user == "revoked"
                else ["medical", "medical-2"]}

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_user] = user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def enter(client, user="ana", account="medical", key=None, replace=None):
    return await client.post("/v1/shifts/check-in",
        headers={"X-Test-User": user, "Idempotency-Key": key or str(uuid4())},
        json={"account_id": account, "replace_shift_id": replace})


async def leave(client, shift, user="ana", key=None):
    return await client.post("/v1/shifts/check-out",
        params={"account_id": shift["account_id"], "shift_id": shift["id"]},
        headers={"X-Test-User": user, "Idempotency-Key": key or str(uuid4())})


async def test_persistent_entry_exit_and_retries(api):
    client, factory = api
    start = await enter(client, key="start")
    assert start.status_code == 201
    shift = start.json()
    assert shift["ended_at"] is None
    assert shift["started_at"].endswith("+00:00")
    # A new request/session sees the persisted entry, without browser state.
    active = await client.get("/v1/shifts/active", params={"account_id": "medical"})
    assert active.json() == shift
    assert (await enter(client, key="start")).json() == shift
    assert (await enter(client)).json() == shift
    closed = await leave(client, shift, key="stop")
    assert closed.status_code == 200
    assert closed.json()["end_reason"] == "manual"
    assert closed.json()["ended_at"] >= shift["started_at"]
    assert (await leave(client, shift, key="stop")).json() == closed.json()
    # Replaying an old entry must not reopen a closed shift.
    assert (await enter(client, key="start")).json() == shift
    assert (await client.get("/v1/shifts/active?account_id=medical")).json() is None
    async with factory() as session:
        assert len((await session.scalars(select(Shift))).all()) == 1


async def test_accounts_run_independently_and_handover_is_atomic(api):
    client, _ = api
    first = (await enter(client)).json()
    parallel = (await enter(client, user="bea", account="medical-2")).json()
    assert (await enter(client, user="bea")).status_code == 409
    next_shift = await enter(client, user="bea", replace=first["id"])
    assert next_shift.status_code == 201
    old = (await client.get("/v1/shifts/history")).json()["items"][0]
    assert old["ended_at"] == next_shift.json()["started_at"]
    assert old["end_reason"] == "handover" and old["closed_by"] == "bea"
    assert (await client.get("/v1/shifts/active?account_id=medical-2")).json() == parallel
    assert (await leave(client, first)).status_code == 409
    assert (await leave(client, next_shift.json())).status_code == 403
    assert (await client.get("/v1/shifts/active?account_id=medical")).json() == next_shift.json()


async def test_simultaneous_entries_do_not_overwrite_each_other(api):
    client, factory = api
    responses = await asyncio.gather(enter(client, user="ana"), enter(client, user="bea"))
    assert sorted(r.status_code for r in responses) == [201, 409]
    async with factory() as session:
        assert len((await session.scalars(select(Shift))).all()) == 1


async def test_concurrent_duplicate_request_is_idempotent(api):
    client, _ = api
    responses = await asyncio.gather(enter(client, key="double-tap"),
                                      enter(client, key="double-tap"))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()


async def test_stale_handover_cannot_replace_a_new_turn(api):
    client, _ = api
    first = (await enter(client)).json()
    results = await asyncio.gather(enter(client, user="bea", replace=first["id"]),
                                    enter(client, user="carla", replace=first["id"]))
    assert sorted(r.status_code for r in results) == [201, 409]
    active = (await client.get("/v1/shifts/active?account_id=medical")).json()
    assert active["id"] == next(r.json()["id"] for r in results if r.status_code == 201)


async def test_idempotency_keys_are_bound_to_user_and_payload(api):
    client, _ = api
    first = (await enter(client, key="shared-key")).json()
    assert (await enter(client, key="shared-key", account="medical-2")).status_code == 409
    assert (await enter(client, key="shared-key", account="medical-2", user="bea")).status_code == 201
    assert (await leave(client, first, key="shared-key")).status_code == 409


async def test_history_is_private_paginated_and_keeps_relieved_turns(api):
    client, _ = api
    for _ in range(3):
        shift = (await enter(client)).json()
        assert (await leave(client, shift)).status_code == 200
    await enter(client, user="bea")
    page = (await client.get("/v1/shifts/history?limit=2")).json()
    assert len(page["items"]) == 2 and page["next_offset"] == 2
    tail = (await client.get("/v1/shifts/history?limit=2&offset=2")).json()
    assert len(tail["items"]) == 1 and tail["next_offset"] is None
    assert all(s["user_id"] == "ana" for s in page["items"] + tail["items"])
    assert len({s["id"] for s in page["items"] + tail["items"]}) == 3
    assert (await client.get("/v1/shifts/history?limit=0")).status_code == 422


async def test_revoked_user_and_missing_key_cannot_write(api):
    client, factory = api
    assert (await enter(client, user="revoked")).status_code == 403
    assert (await client.post("/v1/shifts/check-in", json={"account_id": "medical"})).status_code == 422
    assert (await client.get("/v1/shifts/active?account_id=unknown")).status_code == 403
    async with factory() as session:
        assert not (await session.scalars(select(Shift))).all()
