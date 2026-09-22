"""Worker: procesa eventos -> reconciliacion + metricas, idempotente por event_id."""


async def handle_event(event: dict):
    # TODO: deduplicar por event_id (UNIQUE), conciliar LIVE<->turno, actualizar metricas.
    # Reprocesar el mismo event_id debe ser no-op.
    return {"deduped": False}
