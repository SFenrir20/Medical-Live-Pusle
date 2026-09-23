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


def get_current_user(credentials=Depends(security)):
    if credentials is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    issuer = settings.clerk_issuer.rstrip("/")
    if not issuer.startswith("https://") or not settings.clerk_authorized_parties:
        raise HTTPException(503, "Clerk no está configurado en el servidor.")
    try:
        token = credentials.credentials
        key = jwks_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "sub", "sid"],
                     "verify_aud": False},
        )
        # Native sessions may omit azp. When present, require an explicit origin match.
        if "azp" in claims and claims["azp"] not in settings.clerk_authorized_parties:
            raise jwt.InvalidTokenError("Untrusted authorized party")
        if not claims["sub"] or not claims["sid"] or claims.get("sts") == "pending":
            raise jwt.InvalidTokenError("Incomplete session")
    except PyJWKClientConnectionError as exc:
        raise HTTPException(503, "No se pudo verificar la sesión. Inténtalo otra vez.") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Sesión inválida o vencida.",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    accounts = settings.livepulse_user_accounts.get(claims["sub"], [])
    return {"id": claims["sub"], "accounts": accounts,
            "status": "approved" if accounts else "pending"}
