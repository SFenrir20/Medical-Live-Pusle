"""Process events transactionally; failures leave events available for retry."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert

from ..modules.analytics.models import EventFact, MonitorState
from ..modules.analytics.processor import handle_event  # noqa: F401
from ..modules.broadcasts.models import RawEvent
from ..shared.db import SessionLocal

log = logging.getLogger(__name__)


async def process_batch(factory=SessionLocal, limit=100):
    processed = 0
    async with factory() as session, session.begin():
        rows = (await session.scalars(select(RawEvent.event_id).where(
            RawEvent.broadcast_id.is_not(None),
            ~exists(select(EventFact.event_id).where(EventFact.event_id == RawEvent.event_id)))
            .order_by(RawEvent.occurred_at, RawEvent.event_id).limit(limit)
            .with_for_update(skip_locked=True))).all()
        for event_id in rows:
            await handle_event(session, event_id)
            processed += 1
    return processed


async def run_forever(poll_s=2):
    while True:
        try:
            await process_batch()
            async with SessionLocal() as session, session.begin():
                now = datetime.now(timezone.utc)
                await session.execute(insert(MonitorState).values(
                    account_id='worker', status='running', observed_at=now).on_conflict_do_update(
                    index_elements=['account_id'], set_={'status': 'running', 'observed_at': now}))
        except Exception:
            log.exception('Event processing failed; transaction rolled back')
        await asyncio.sleep(poll_s)


if __name__ == '__main__':
    asyncio.run(run_forever())
