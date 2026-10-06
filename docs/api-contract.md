# Contrato API v1

Todas las rutas `/v1` requieren Bearer token de Clerk. `GET /health` es público.

## Perfil

`GET /v1/me` devuelve `{id, status, accounts}`. La autorización para marcar se evalúa en cada petición.

## Turnos

- `GET /v1/shifts/active?account_id=medical`: turno de esa cuenta o `null`. Requiere acceso a la cuenta.
- `POST /v1/shifts/check-in`: JSON `{account_id, replace_shift_id?: string|null}` + header `Idempotency-Key` obligatorio. Devuelve 201 con turno. Si está libre, `replace_shift_id` debe ser null; para relevar debe coincidir con el turno observado/confirmado. Si ya hay un turno propio, devuelve ese mismo turno.
- `POST /v1/shifts/check-out?account_id=medical&shift_id=UUID`: `Idempotency-Key` obligatorio. Devuelve 200 con turno cerrado. Solo puede cerrar el propio turno identificado, nunca uno posterior.
- `GET /v1/shifts/history?limit=20&offset=0`: `{items: Shift[], next_offset: number|null}`. Solo historial propio, orden descendente por entrada/ID, límite 1–100.

Shift: `{id, account_id, user_id, started_at, ended_at, end_reason, closed_by}`.
Fechas ISO 8601 con zona UTC. `ended_at`, `end_reason`, `closed_by` son null mientras está abierto. Motivos de cierre: `manual` o `handover`.

Errores: 401 sesión inválida, 403 cuenta/turno no autorizado, 409 turno cambiado o clave reutilizada con otra petición, 422 campos faltantes/inválidos.
Reintentar una marcación usa exactamente la misma clave y contenido. Una respuesta idempotente describe el resultado original: consultar después `/active` para el estado actual.

No se usa el reloj del cliente ni se almacenan coordenadas. Ver `shifts.md` para reglas y pruebas de relevo.
