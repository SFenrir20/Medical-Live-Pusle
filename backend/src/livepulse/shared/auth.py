from functools import lru_cache

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
    return {"id": claims["sub"]}


def get_current_user(credentials=Depends(security)):
    if credentials is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return verify_token(credentials.credentials)
