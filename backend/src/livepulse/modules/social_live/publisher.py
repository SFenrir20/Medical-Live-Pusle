"""Bridge from the TikTok monitor (broadcasts/raw_events) to the Social Live model
(lives/live_metrics/captured_phones).

Capturing a LIVE must show up in the new reports, so the worker runs `publish_batch` on every
tick. It is idempotent: each raw event is claimed once through live_event_keys, so reruns,
restarts and parallel workers never double count. A live is the broadcast (account and real
time window); the host remains unassigned unless explicitly supplied."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...shared.config import settings
from ..broadcasts.models import Broadcast, RawEvent
from .models import Live, LiveMetrics, TiktokAccount
from .schemas import EventIn
from .service import aware_utc, finish_live, ingest, utcnow

PREFIX = 'TT-'
BATCH = 200


def live_id_for(broadcast_id: int) -> str:
    return f'{PREFIX}{broadcast_id}'


def _count(value, default=1):
    try:
        return max(0, min(int(value), 2_000_000_000))
    except (TypeError, ValueError):
        return default


async def ensure_live(session, broadcast: Broadcast) -> Live:
    live = await session.get(Live, live_id_for(broadcast.id))
    if live is not None:
        return live
    account = await session.get(TiktokAccount, broadcast.account_id)
    if account is None:
        try:
            async with session.begin_nested():
                session.add(TiktokAccount(
                    id=broadcast.account_id, name=broadcast.account_id,
                    username=broadcast.tiktok_username))
                await session.flush()
        except IntegrityError:
            pass  # another worker created it
    now = utcnow()
    ended = broadcast.ended_at
    live = Live(id=live_id_for(broadcast.id), account_id=broadcast.account_id,
                tiktoker_id=None, started_at=broadcast.started_at,
                status='finished' if ended else 'live', ended_at=ended,
                duration_seconds=int((aware_utc(ended) - aware_utc(broadcast.started_at))
                                     .total_seconds()) if ended else None,
                created_at=now, updated_at=now)
    session.add(live)
    session.add(LiveMetrics(live_id=live.id, created_at=now, updated_at=now))
    await session.flush()
    return live


def to_event(raw: RawEvent) -> EventIn | None:
    """Raw provider event -> ingestion event. None = nothing to count."""
    payload = raw.payload or {}
    at = min(aware_utc(raw.occurred_at), utcnow())
    common = {'timestamp': at, 'event_id': raw.event_id}
    kind = raw.type
    user = str(payload.get('username') or payload.get('nickname') or payload.get('user') or '')
    user = user.strip()[:128] or None
    if kind == 'comment':
        text = (raw.raw_text or '').strip()
        if not text or not user:
            return None
        return EventIn(event_type='comment', username=user, text=text[:2000], **common)
    if kind == 'like':
        return EventIn(event_type='like', value=_count(payload.get('count'), 1), **common)
    if kind == 'share':
        return EventIn(event_type='share', username=user, **common)
    if kind == 'follow':
        return EventIn(event_type='follow', username=user, **common)
    if kind == 'join':
        return EventIn(event_type='view', username=user, **common)
    if kind == 'audience':
        if payload.get('viewers') is None:
            return None
        return EventIn(event_type='viewer', value=_count(payload.get('viewers'), 0), **common)
    if kind == 'gift':
        # Streaks report intermediate ticks; count only the final one (same rule as analytics).
        final = _count(payload.get('gift_type'), 0) != 1 or _count(payload.get('repeat_end'), 0) == 1
        quantity = max(1, _count(payload.get('repeat_count'), 1)) if final else 0
        if not quantity:
            return None
        return EventIn(event_type='donation', username=user, value=quantity, **common)
    return None  # live_end etc.: the lifecycle store already closes the broadcast


async def publish_batch(factory, limit: int = BATCH) -> int:
    """Fold up to `limit` unpublished raw events into the read model. Returns how many were
    examined.

    Idempotency lives on the raw event itself (raw_events.published_at), so it survives the
    retention purge of live_event_keys: old events are never counted twice. The whole history
    is converted (oldest first); comment text older than the retention window is not stored
    because the daily purge would drop it anyway, but its counters and phones are."""
    cutoff = utcnow() - timedelta(days=settings.comments_retention_days)
    done = 0
    async with factory() as session, session.begin():
        pending = (await session.execute(
            select(RawEvent, Broadcast).join(Broadcast, Broadcast.id == RawEvent.broadcast_id)
            .where(RawEvent.broadcast_id.is_not(None), RawEvent.published_at.is_(None))
            .order_by(RawEvent.occurred_at, RawEvent.event_id).limit(limit)
            .with_for_update(of=RawEvent, skip_locked=True))).all()
        now = utcnow()
        for raw, broadcast in pending:
            live = await ensure_live(session, broadcast)
            try:
                event = to_event(raw)
            except ValueError:
                event = None
            if event is not None:
                try:
                    async with session.begin_nested():
                        await ingest(session, live, event, strict_age=False,
                                     store_detail=aware_utc(raw.occurred_at) >= cutoff)
                except HTTPException:
                    pass  # cancelled/finished live or invalid detail: never retried forever
            raw.published_at = now
            done += 1
    await sync_status(factory)
    return done


async def sync_status(factory) -> None:
    """Keep each live's status/end aligned with its broadcast (confirmed end, rejoin)."""
    async with factory() as session, session.begin():
        open_lives = (await session.scalars(select(Live).where(
            Live.id.like(PREFIX + '%'), Live.status == 'live'))).all()
        recent_cut = utcnow() - timedelta(days=1)
        closed_lives = (await session.scalars(select(Live).where(
            Live.id.like(PREFIX + '%'), Live.status == 'finished',
            Live.ended_at >= recent_cut))).all()
        ids = {int(live.id[len(PREFIX):]) for live in open_lives + closed_lives
               if live.id[len(PREFIX):].isdigit()}
        if not ids:
            return
        broadcasts = {b.id: b for b in (await session.scalars(
            select(Broadcast).where(Broadcast.id.in_(ids)))).all()}
        for live in open_lives:
            broadcast = broadcasts.get(int(live.id[len(PREFIX):]))
            if broadcast is not None and broadcast.ended_at is not None:
                await finish_live(session, live, broadcast.ended_at, 'finished')
        for live in closed_lives:
            broadcast = broadcasts.get(int(live.id[len(PREFIX):]))
            if broadcast is not None and broadcast.ended_at is None:
                live.status, live.ended_at, live.duration_seconds = 'live', None, None
                live.updated_at = utcnow()
