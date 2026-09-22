# Contrato API v1 (borrador)

Reglas:
- `account_id` siempre requerido en turnos/LIVEs. Un turno activo por `account_id`.
- Reintentos con header `Idempotency-Key`.
- Backend compatible con apps viejas: no romper `/v1/`, versionar `/v2/` si cambia.

## Turnos
- `GET /health` -> `{ok:true}`
- `GET /v1/shifts/active?account_id=medical` (auth) -> turno activo o null
- `POST /v1/shifts/check-in {account_id, lat?, lng?}` + `Idempotency-Key` -> 201 turno abierto. Si hay relevo, cierra anterior de esa cuenta y abre nuevo en una operacion.
- `POST /v1/shifts/check-out?account_id=medical` + `Idempotency-Key` -> 200 turno cerrado

Errores: 401 sin token, 403 cuenta no autorizada, 409 ya hay turno activo en relevo mal formado.
