"""Turnos: 1 activo por account_id, relevo cierra anterior y abre nuevo.

DB debe tener indice unico parcial:
  CREATE UNIQUE INDEX uq_active_shift_per_account
  ON shifts(account_id) WHERE ended_at IS NULL;
"""

from fastapi import HTTPException


def require_account(account_id: str, user: dict):
    if account_id not in user.get("accounts", []):
        raise HTTPException(status_code=403, detail="Cuenta no autorizada")


def unavailable():
    raise HTTPException(status_code=501, detail="Persistencia de turnos pendiente de implementar")


async def check_in(*, account_id: str, user: dict, idempotency_key: str | None):
    require_account(account_id, user)
    # TODO: SELECT FOR UPDATE + insert con manejo de Idempotency-Key.
    unavailable()


async def check_out(*, account_id: str, user: dict, idempotency_key: str | None):
    require_account(account_id, user)
    unavailable()
