import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from livepulse.entrypoints.api import app
from livepulse.modules.tiktok_oauth import api
from livepulse.modules.tiktok_oauth.models import OAuthAttempt, OAuthConnection
from livepulse.shared.auth import get_current_user
from livepulse.shared.config import settings
from livepulse.shared.db import Base, get_session

PREFIX = "/api/integrations/tiktok"


@pytest.fixture
async def env(monkeypatch):
    for key, value in {
        "tiktok_app_id": "app-123", "tiktok_app_secret": "secret-123",
        "tiktok_redirect_uri": "https://social.test" + api.CALLBACK,
        "tiktok_token_encryption_key": Fernet.generate_key().decode(),
        "admin_user_ids": [],
    }.items():
        monkeypatch.setattr(settings, key, value)
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[
            OAuthAttempt.__table__, OAuthConnection.__table__,
        ]))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        async with factory() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_user] = lambda: {"id": "manager-1", "role": "gerente"}
    calls = []
    reply = {"code": 0, "data": {"access_token": "private-token", "advertiser_ids": [123],
                                 "scope": [4]}}

    async def post(self, url, **kwargs):
        calls.append((url, kwargs))
        if reply.get("timeout"):
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))

    # Patch post only for the remote client. ASGI test client still uses its real post.
    original = httpx.AsyncClient.post

    async def dispatch(self, url, **kwargs):
        if str(url).startswith("https://business-api.tiktok.com/"):
            return await post(self, url, **kwargs)
        return await original(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", dispatch)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://social.test") as client:
            yield client, factory, calls, reply
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def start(client):
    response = await client.post(PREFIX + "/authorize")
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    url = urlsplit(response.json()["authorization_url"])
    assert url.netloc == "business-api.tiktok.com"
    params = parse_qs(url.query)
    assert params["redirect_uri"] == [settings.tiktok_redirect_uri]
    assert params["app_id"] == ["app-123"]
    return params["state"][0]


async def test_callback_public_landing_and_authenticated_start(env):
    client, _, calls, _ = env
    app.dependency_overrides.pop(get_current_user)
    response = await client.get(api.CALLBACK)
    assert response.status_code == 200
    assert "Inicia la autorización" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert (await client.post(PREFIX + "/authorize")).status_code == 401
    assert (await client.get(PREFIX + "/status")).status_code == 401
    assert not calls


@pytest.mark.parametrize("role", ["agente_ventas", None])
async def test_agents_cannot_connect_or_read_credentials(env, role):
    client, _, calls, _ = env
    app.dependency_overrides[get_current_user] = lambda: {"id": "agent", "role": role}
    assert (await client.post(PREFIX + "/authorize")).status_code == 403
    assert (await client.get(PREFIX + "/status")).status_code == 403
    assert not calls


async def test_success_encrypted_persistent_and_no_replay(env):
    client, factory, calls, _ = env
    state = await start(client)
    browser = client.cookies.get(api.COOKIE)
    async with factory() as session:
        attempt = await session.get(OAuthAttempt, api.digest(state))
        assert attempt is not None and attempt.browser_hash != browser
    response = await client.get(api.CALLBACK, params={"state": state, "auth_code": "one-use-code"})
    assert response.status_code == 303
    assert response.headers["location"] == "/integraciones/tiktok?resultado=connected"
    assert "one-use-code" not in response.text and "private-token" not in response.text
    assert calls[0][1]["json"] == {"app_id": "app-123", "secret": "secret-123", "auth_code": "one-use-code"}
    async with factory() as session:
        connection = (await session.scalars(select(OAuthConnection))).one()
        assert connection.token_encrypted != "private-token"
        assert api.cipher().decrypt(connection.token_encrypted.encode()) == b"private-token"
        assert connection.authorized_by == "manager-1"
        assert connection.advertiser_ids == ["123"]
        assert await session.get(OAuthAttempt, api.digest(state)) is None
    status = await client.get(PREFIX + "/status")
    assert status.json()["configured"] is True
    assert "token" not in status.text and "secret" not in status.text
    replay = await client.get(api.CALLBACK, params={"state": state, "auth_code": "one-use-code"},
                              headers={"Cookie": f"{api.COOKIE}={browser}"})
    assert replay.headers["location"].endswith("=invalid")
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["missing_cookie", "wrong_cookie", "wrong_state", "expired", "changed_app", "changed_uri"])
async def test_invalid_attempt_never_exchanges(env, monkeypatch, failure):
    client, factory, calls, _ = env
    state = await start(client)
    if failure in {"missing_cookie", "wrong_cookie"}:
        client.cookies.clear()
        if failure == "wrong_cookie":
            client.cookies.set(api.COOKIE, "other-browser")
    if failure == "wrong_state":
        state = "wrong"
    if failure == "expired":
        async with factory() as session:
            await session.execute(update(OAuthAttempt).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
            await session.commit()
    if failure == "changed_app":
        monkeypatch.setattr(settings, "tiktok_app_id", "different")
    if failure == "changed_uri":
        monkeypatch.setattr(settings, "tiktok_redirect_uri", "https://other.test" + api.CALLBACK)
    response = await client.get(api.CALLBACK, params={"state": state, "auth_code": "code"})
    assert response.headers["location"].endswith("=invalid")
    assert not calls


async def test_denial_is_not_echoed_and_attempt_is_consumed(env):
    client, factory, calls, _ = env
    state = await start(client)
    response = await client.get(api.CALLBACK, params={"state": state, "error": "<script>secret</script>"})
    assert response.headers["location"].endswith("=denied")
    assert "secret" not in response.text
    async with factory() as session:
        assert await session.get(OAuthAttempt, api.digest(state)) is None
    assert not calls


@pytest.mark.parametrize("reply", [
    {"code": 40001, "message": "sensitive-detail"}, {"timeout": True},
    {"code": 0, "data": {"access_token": "private-token"}},
    {"code": 0, "data": {"access_token": "", "advertiser_ids": []}},
])
async def test_exchange_failure_does_not_save_or_expose_token(env, reply):
    client, factory, _, remote = env
    remote.clear()
    remote.update(reply)
    state = await start(client)
    response = await client.get(api.CALLBACK, params={"state": state, "auth_code": "code"})
    assert response.headers["location"].endswith("=exchange_failed")
    async with factory() as session:
        assert not (await session.scalars(select(OAuthConnection))).all()


@pytest.mark.parametrize("field,value", [("tiktok_app_secret", ""), ("tiktok_token_encryption_key", "bad"),
                                        ("tiktok_redirect_uri", "http://insecure.test" + api.CALLBACK)])
async def test_missing_configuration_is_explicit(env, monkeypatch, field, value):
    client, _, calls, _ = env
    monkeypatch.setattr(settings, field, value)
    assert (await client.get(PREFIX + "/status")).json()["configured"] is False
    assert (await client.post(PREFIX + "/authorize")).status_code == 503
    assert not calls


def test_uvicorn_callback_query_redacted():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s %s %s %s %s',
                               ("client", "GET", api.CALLBACK + "?auth_code=secret&state=secret", "1.1", 303), None)
    assert api.CallbackLogFilter().filter(record)
    assert "secret" not in record.getMessage()
