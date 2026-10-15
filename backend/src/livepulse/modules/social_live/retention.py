"""Comment retention. Only temporary detail is removed; lives, live_metrics and
captured_phones are permanent."""
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from ...shared.config import settings
from .models import Live, LiveComment, LiveEventKey
from .service import utcnow

log = logging.getLogger(__name__)
BATCH = 5000


async def purge_expired(factory, days: int | None = None) -> dict:
    days = settings.comments_retention_days if days is None else days
    cutoff = utcnow() - timedelta(days=days)
    removed = {'comments': 0, 'event_keys': 0}
    while True:
        async with factory() as session, session.begin():
            ids = (await session.scalars(select(LiveComment.id).where(
                LiveComment.created_at < cutoff).limit(BATCH))).all()
            if not ids:
                break
            await session.execute(delete(LiveComment).where(LiveComment.id.in_(ids)))
            removed['comments'] += len(ids)
    # Keys protect against duplicate metrics, so they are kept while their live can still
    # receive events. Only finished/cancelled lives (which reject new events) lose them.
    while True:
        async with factory() as session, session.begin():
            closed = select(Live.id).where(Live.status.in_(('finished', 'cancelled')),
                                           Live.ended_at < cutoff)
            pairs = (await session.execute(select(LiveEventKey.live_id, LiveEventKey.event_id)
                     .where(LiveEventKey.live_id.in_(closed)).limit(BATCH))).all()
            if not pairs:
                break
            for live_id, event_id in pairs:
                await session.execute(delete(LiveEventKey).where(
                    LiveEventKey.live_id == live_id, LiveEventKey.event_id == event_id))
            removed['event_keys'] += len(pairs)
    if any(removed.values()):
        log.info('Retention purge (%s days): %s', days, removed)
    return removed
