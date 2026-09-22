"""Turnos: 1 activo por account_id, relevo cierra anterior y abre nuevo.

DB debe tener indice unico parcial:
  CREATE UNIQUE INDEX uq_active_shift_per_account
  ON shifts(account_id) WHERE ended_at IS NULL;
"""


async def check_in(*, account_id: str, user: dict, idempotency_key: str | None):
    if account_id not in user.get("accounts", []):
        raise PermissionError("Cuenta no autorizada")
    # TODO: SELECT FOR UPDATE + insert con manejo de Idempotency-Key.
    return {"account_id": account_id, "status": "open", "idempotency_key": idempotency_key}


async def check_out(*, account_id: str, user: dict, idempotency_key: str | None):
    return {"account_id": account_id, "status": "closed"}
