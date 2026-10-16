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

from fastapi import Header, HTTPException

from ...shared import auth as clerk
from ...shared.config import settings
from ..identity.roles import permissions_of, role_for


def _scopes(token: str) -> set[str]:
    granted: set[str] = set()
    for secret, scopes in ((settings.social_live_token, {'ingest'}),
                           (settings.medical360_token, {'read', 'contacts:read_all'}),
                           (settings.medical360_export_token,
                            {'read', 'export', 'contacts:read_all'})):
        if secret and hmac.compare_digest(secret.encode(), token.encode()):
            granted |= scopes
    return granted


def require_scope(*scopes: str):
    """Pass if the caller holds ANY of the given scopes."""

    async def dependency(authorization: str = Header(default='')):
        kind, _, token = authorization.partition(' ')
        token = token.strip()
        if kind.lower() != 'bearer' or not token:
            raise HTTPException(401, 'Falta el token de acceso.',
                                headers={'WWW-Authenticate': 'Bearer'})
        granted = _scopes(token)
        if granted:
            if not granted & set(scopes):
                raise HTTPException(403, 'El token no tiene permiso para esta operación.')
            return {'kind': 'service', 'scopes': granted}
        if not clerk.clerk_configured():
            raise HTTPException(401, 'Token de servicio inválido.',
                                headers={'WWW-Authenticate': 'Bearer'})
        person = clerk.verify_token(token)  # 401/503 if the session is not valid
        role = role_for(person['id'], person.get('role'))
        if role is None:
            raise HTTPException(403, 'Tu usuario no tiene un rol asignado en Clerk.')
        if not permissions_of(role) & set(scopes):
            raise HTTPException(403, 'Tu rol no tiene permiso para esta operación.')
        return {'kind': 'user', 'user_id': person['id'], 'role': role}
    return dependency
