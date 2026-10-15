"""Metrics over persisted capture facts for the Medical 360 bridge."""
from sqlalchemy import case, distinct, func, select

from ..broadcasts.models import Broadcast, RawEvent
from .models import EventFact as F


def aggregates():
    return [func.count(F.event_id).label('events'),
            func.coalesce(func.sum(F.comments), 0).label('comments'),
            func.coalesce(func.sum(F.likes), 0).label('likes'),
            func.coalesce(func.sum(F.shares), 0).label('shares'),
            func.coalesce(func.sum(F.gifts), 0).label('gifts'),
            func.coalesce(func.sum(F.diamonds), 0).label('diamonds'),
            func.max(F.viewers).label('peak_viewers'),
            func.avg(F.viewers).label('average_sampled_viewers'),
            func.count(distinct(F.user_key)).label('observed_users'),
            func.count(distinct(case((F.kind == 'follow', F.user_key)))).label('observed_followers'),
            func.count(distinct(case((F.gifts > 0, F.user_key)))).label('donors'),
            func.count(distinct(case((F.interested.is_(True), F.user_key)))).label('interested_users'),
            func.count(distinct(F.lead_id)).label('leads')]


async def lives(session, account=None, limit=20, offset=0):
    query = select(Broadcast).order_by(Broadcast.started_at.desc(), Broadcast.id.desc())
    if account:
        query = query.where(Broadcast.account_id == account)
    rows = (await session.scalars(query.offset(offset).limit(limit + 1))).all()
    items = []
    for broadcast in rows[:limit]:
        stats = (await session.execute(select(*aggregates()).where(F.broadcast_id == broadcast.id)))
        values = dict(stats.mappings().one())
        values['average_sampled_viewers'] = (float(values['average_sampled_viewers'])
            if values['average_sampled_viewers'] is not None else None)
        raw = await session.scalar(select(func.count()).select_from(RawEvent)
                                   .where(RawEvent.broadcast_id == broadcast.id))
        items.append({'id': broadcast.id, 'account_id': broadcast.account_id,
                      'username': broadcast.tiktok_username, 'room_id': broadcast.room_id,
                      'started_at': broadcast.started_at, 'ended_at': broadcast.ended_at,
                      'end_confirmed': broadcast.end_confirmed, 'start_source': 'first_observed',
                      'pending_events': raw - values['events'], 'metrics': values,
                      'direct_messages': None, 'total_unique_viewers': None})
    return {'items': items, 'next_offset': offset + limit if len(rows) > limit else None}
