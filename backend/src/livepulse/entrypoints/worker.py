"""Worker: procesa eventos -> reconciliacion + metricas, idempotente por event_id."""
from datetime import datetime, timezone

from sqlalchemy import select, update

from ..modules.broadcasts.models import RawEvent


async def handle_event(session, event_id: str) -> dict:
    """Procesa un RawEvent. Reprocesar el mismo event_id es no-op."""
    row = (await session.execute(select(RawEvent).where(RawEvent.event_id == event_id))).scalar_one_or_none()
    if row is None:
        return {"status": "unknown-event", "deduped": False}
    if row.processed_at is not None:
        return {"status": "already-processed", "deduped": True}
    # TODO: conciliar LIVE<->turno por (account_id, intervalo) y agregar metricas
    # (comentarios, regalos, joins) + extraer telefonos a contacts.
    await session.execute(
        update(RawEvent).where(RawEvent.event_id == event_id).values(
            processed_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return {"status": "processed", "deduped": False}


async def run_forever(poll_s: float = 2.0):
    import asyncio

    from ..shared.db import SessionLocal

    while True:
        async with SessionLocal() as session:
            rows = (await session.execute(
                select(RawEvent.event_id).where(RawEvent.processed_at.is_(None)).limit(100)
            )).scalars().all()
            for event_id in rows:
                await handle_event(session, event_id)
        await asyncio.sleep(poll_s)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_forever())
