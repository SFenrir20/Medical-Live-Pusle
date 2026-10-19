import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.auth import get_current_user
from ...shared.config import settings
from ...shared.db import get_session
from ..identity.roles import role_for
from .models import OAuthAttempt, OAuthConnection

PREFIX = "/api/integrations/tiktok"
CALLBACK = f"{PREFIX}/callback"
COOKIE = "__Secure-tiktok-oauth"
HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
router = APIRouter(prefix=PREFIX, tags=["TikTok authorization"])


class CallbackLogFilter(logging.Filter):
    """Uvicorn logs query strings by default, including single-use authorization codes."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split("?", 1)[0] == CALLBACK:
                args[2] = CALLBACK
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(CallbackLogFilter())


def manager(user=Depends(get_current_user)):
    if role_for(user["id"], user.get("role")) not in {
        "admin", "gerente", "jefe_marketing", "supervisor",
    }:
        raise HTTPException(403, "Tu rol no permite conectar TikTok.")
    return user


def cipher() -> Fernet:
    try:
        return Fernet(settings.tiktok_token_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Falta configurar la conexión con TikTok en el servidor.") from None


def configured() -> bool:
    uri = urlsplit(settings.tiktok_redirect_uri)
    if not (settings.tiktok_app_id and settings.tiktok_app_secret
            and uri.scheme == "https" and uri.hostname and uri.path == CALLBACK
            and not uri.query and not uri.fragment and not uri.username and not uri.password):
        return False
    try:
        cipher()
    except HTTPException:
        return False
    return True


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def result(outcome: str):
    # Only fixed result codes go to the browser, never TikTok's response or credentials.
    response = RedirectResponse(f"/integraciones/tiktok?resultado={outcome}", 303,
                                headers=HEADERS)
    response.delete_cookie(COOKIE, path=CALLBACK, secure=True, httponly=True, samesite="lax")
    return response


@router.get("/status")
async def status(user=Depends(manager), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(OAuthConnection).where(
        OAuthConnection.app_id == settings.tiktok_app_id
    ).order_by(OAuthConnection.authorized_at.desc()).limit(20))).all()
    return JSONResponse({"configured": configured(), "connections": [
        {"id": row.id, "authorized_at": row.authorized_at.isoformat(),
         "advertiser_ids": row.advertiser_ids} for row in rows
    ]}, headers=HEADERS)


@router.post("/authorize")
async def authorize(user=Depends(manager), session: AsyncSession = Depends(get_session)):
    if not configured():
        raise HTTPException(503, "Falta configurar la conexión con TikTok en el servidor.")
    now = datetime.now(UTC)
    state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    await session.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at <= now))
    session.add(OAuthAttempt(state_hash=digest(state), browser_hash=digest(browser),
                             user_id=user["id"], app_id=settings.tiktok_app_id,
                             redirect_uri=settings.tiktok_redirect_uri,
                             expires_at=now + timedelta(minutes=10)))
    await session.commit()
    url = "https://business-api.tiktok.com/portal/auth?" + urlencode({
        "app_id": settings.tiktok_app_id, "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
    })
    response = JSONResponse({"authorization_url": url}, headers=HEADERS)
    response.set_cookie(COOKIE, browser, max_age=600, path=CALLBACK,
                        secure=True, httponly=True, samesite="lax")
    return response


@router.get("/callback")
async def callback(request: Request, session: AsyncSession = Depends(get_session)):
    params = request.query_params
    if not params:
        return HTMLResponse(
            '<!doctype html><html lang="es"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Conectar TikTok | Social Pulse</title><body>'
            '<h1>Conexión con TikTok</h1><p>Inicia la autorización desde Social Pulse.</p>'
            '<a href="/integraciones/tiktok">Abrir conexión con TikTok</a></body></html>',
            headers={**HEADERS, "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"},
        )
    state, browser = params.get("state", ""), request.cookies.get(COOKIE, "")
    if not state or not browser or len(state) > 200 or len(browser) > 200:
        return result("invalid")
    if not configured():
        return result("configuration")
    # Atomic consume: a callback can be processed only once, including across API workers.
    attempt = (await session.execute(delete(OAuthAttempt).where(
        OAuthAttempt.state_hash == digest(state), OAuthAttempt.browser_hash == digest(browser),
        OAuthAttempt.expires_at > datetime.now(UTC),
        OAuthAttempt.app_id == settings.tiktok_app_id,
        OAuthAttempt.redirect_uri == settings.tiktok_redirect_uri,
    ).returning(OAuthAttempt.user_id))).scalar_one_or_none()
    await session.commit()
    if attempt is None:
        return result("invalid")
    if params.get("error"):
        return result("denied")
    code = params.get("auth_code", "")
    if not code or len(code) > 4096:
        return result("invalid")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
                json={"app_id": settings.tiktok_app_id, "secret": settings.tiktok_app_secret,
                      "auth_code": code},
            )
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data")
        if payload.get("code") != 0 or not isinstance(data, dict):
            return result("exchange_failed")
        token = data.get("access_token")
        advertisers, scopes = data.get("advertiser_ids"), data.get("scope", [])
        if not isinstance(token, str) or not token or not isinstance(advertisers, list):
            return result("exchange_failed")
        if not isinstance(scopes, list) or any(not isinstance(v, (str, int)) for v in advertisers):
            return result("exchange_failed")
    except (httpx.HTTPError, ValueError, AttributeError):
        return result("exchange_failed")
    session.add(OAuthConnection(
        id=str(uuid4()), app_id=settings.tiktok_app_id, authorized_by=attempt,
        authorized_at=datetime.now(UTC), token_encrypted=cipher().encrypt(token.encode()).decode(),
        advertiser_ids=[str(v) for v in advertisers], scopes=scopes,
    ))
    await session.commit()
    return result("connected")
