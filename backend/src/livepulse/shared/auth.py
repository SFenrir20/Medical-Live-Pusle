import time
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from .config import settings

security = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def jwks_client(issuer: str):
    return PyJWKClient(f"{issuer}/.well-known/jwks.json", timeout=5)


ROLE_CODES = ('agente_ventas', 'gerente', 'jefe_marketing', 'supervisor')
METADATA_KEY = 'livepulse'
_directory: dict[str, tuple[float, str | None]] = {}
DIRECTORY_TTL = 60.0


def role_in(metadata) -> str | None:
    """Role code from Clerk public metadata ({"livepulse": {"role": "..."}}); None if absent
    or not one of the known codes (a typo grants nothing)."""
    section = metadata.get(METADATA_KEY) if isinstance(metadata, dict) else None
    role = section.get('role') if isinstance(section, dict) else None
    return role if role in ROLE_CODES else None


def role_from_backend_api(user_id: str) -> str | None:
    """Fallback when the session token does not carry the metadata claim. Cached briefly."""
    cached = _directory.get(user_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        response = httpx.get(f'https://api.clerk.com/v1/users/{user_id}', timeout=5,
                             headers={'Authorization': f'Bearer {settings.clerk_secret_key}'})
        response.raise_for_status()
        role = role_in(response.json().get('public_metadata'))
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(503, 'No se pudo consultar el rol en Clerk. Inténtalo otra vez.') from None
    _directory[user_id] = (time.monotonic() + DIRECTORY_TTL, role)
    return role


def clerk_configured() -> bool:
    return (settings.clerk_issuer.rstrip("/").startswith("https://")
            and bool(settings.clerk_authorized_parties))


def verify_token(token: str) -> dict:
    """Validate a Clerk session JWT and return the authenticated identity."""
    issuer = settings.clerk_issuer.rstrip("/")
    if not clerk_configured():
        raise HTTPException(503, "Clerk no está configurado en el servidor.")
    try:
        key = jwks_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "sub", "sid"],
                     "verify_aud": False},
        )
        # When present, azp must match an explicitly authorized origin.
        if "azp" in claims and claims["azp"] not in settings.clerk_authorized_parties:
            raise jwt.InvalidTokenError("Untrusted authorized party")
        if not claims["sub"] or not claims["sid"] or claims.get("sts") == "pending":
            raise jwt.InvalidTokenError("Incomplete session")
    except PyJWKClientConnectionError as exc:
        raise HTTPException(503, "No se pudo verificar la sesión. Inténtalo otra vez.") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Sesión inválida o vencida.",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    # The role is whatever Clerk signed into the token: users cannot edit Public metadata.
    claim = claims.get(settings.clerk_roles_claim)
    if claim is not None:
        role = role_in(claim)
    elif settings.clerk_secret_key:
        role = role_from_backend_api(claims["sub"])
    else:
        role = None
    return {"id": claims["sub"], "role": role}


def get_current_user(credentials=Depends(security)):
    if credentials is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return verify_token(credentials.credentials)
