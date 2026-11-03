"""Encryption of secrets stored in the database (API keys of AI providers, tokens).

Uses Fernet with APP_ENCRYPTION_KEY, or TIKTOK_TOKEN_ENCRYPTION_KEY when the former is not set
(one stable key is enough for the whole deployment). Changing the key makes what was stored
unreadable, so keep it backed up apart from the database."""
from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class SecretsUnavailable(RuntimeError):
    pass


def _cipher() -> Fernet:
    key = settings.app_encryption_key or settings.tiktok_token_encryption_key
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise SecretsUnavailable(
            'Falta configurar APP_ENCRYPTION_KEY (clave Fernet) para guardar claves.') from None


def encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise SecretsUnavailable('No se pudo leer la clave guardada (¿cambió la clave de cifrado?).') from None


def mask(secret: str) -> str:
    """Show only that a key exists and how it ends, never the key."""
    return f'••••{secret[-4:]}' if len(secret) > 8 else '••••'
