"""Destinos de eventos: Postgres (prod) y memoria (tests/manual)."""
from typing import Protocol


class EventSink(Protocol):
    async def emit(self, event: dict) -> bool:
        """Guarda el evento. Retorna True si es nuevo, False si ya existia."""
        ...


class MemorySink:
    def __init__(self):
        self.events: dict[str, dict] = {}

    async def emit(self, event: dict) -> bool:
        if event["event_id"] in self.events:
            return False
        self.events[event["event_id"]] = event
        return True


class PostgresSink:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def emit(self, event: dict) -> bool:
        from sqlalchemy.dialects.postgresql import insert

        from .models import RawEvent

        async with self.session_factory() as session:
            stmt = insert(RawEvent).values(
                event_id=event["event_id"],
                account_id=event["account_id"],
                broadcast_id=event.get("broadcast_id"),
                type=event["type"],
                occurred_at=event.get("occurred_at"),
                payload=event.get("payload", {}),
                raw_text=event.get("raw_text"),
            ).on_conflict_do_nothing(index_elements=["event_id"])
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount == 1
