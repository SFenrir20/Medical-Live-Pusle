"""Authentication for the Social Live / Medical 360 API. Two kinds of caller:

1. A server with a service token (scopes below), compared in constant time.
   ingest -> Medical Social Live creates lives/events/phones and updates contact status.
   read   -> Medical 360 queries statistics.
   export -> authorized exports of detailed comments (also implies read).
2. A signed-in person (Clerk session JWT) whose server-side role grants the scope, so the
   browser never holds a service token. Roles/permissions: modules/identity/roles.py.

An unset token is disabled. People can never obtain `ingest`.
"""
import hmac

from fastapi import Depends, Header, HTTPException

from ...shared import auth as clerk
from ...shared.config import settings
from ...shared.db import get_session
from ..analytics.models import UserRole
from ..identity.roles import PERMISSIONS, role_for


def _scopes(token: str) -> set[str]:
    granted: set[str] = set()
    for secret, scopes in ((settings.social_live_token, {'ingest'}),
                           (settings.medical360_token, {'read'}),
                           (settings.medical360_export_token, {'read', 'export'})):
        if secret and hmac.compare_digest(secret.encode(), token.encode()):
            granted |= scopes
    return granted


def require_scope(scope: str):
    async def dependency(authorization: str = Header(default=''),
                         session=Depends(get_session)):
        kind, _, token = authorization.partition(' ')
        token = token.strip()
        if kind.lower() != 'bearer' or not token:
            raise HTTPException(401, 'Falta el token de acceso.',
                                headers={'WWW-Authenticate': 'Bearer'})
        granted = _scopes(token)
        if granted:
            if scope not in granted:
                raise HTTPException(403, 'El token no tiene permiso para esta operación.')
            return {'kind': 'service', 'scopes': granted}
        if not clerk.clerk_configured():
            raise HTTPException(401, 'Token de servicio inválido.',
                                headers={'WWW-Authenticate': 'Bearer'})
        person = clerk.verify_token(token)  # 401/503 if the session is not valid
        row = await session.get(UserRole, person['id'])
        role = role_for(person['id'], row.role if row else None)
        if scope not in PERMISSIONS[role]:
            raise HTTPException(403, 'Tu rol no tiene permiso para esta operación.')
        return {'kind': 'user', 'user_id': person['id'], 'role': role}
    return dependency
