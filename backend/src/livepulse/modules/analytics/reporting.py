"""Metrics over persisted facts; half-open shifts prevent double attribution at handover."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, case, distinct, func, select

from ..broadcasts.models import Broadcast, RawEvent
from ..shifts.models import Shift
from .models import EventFact as F


def shift_join():
    return and_(Shift.account_id == F.account_id, Shift.started_at <= F.occurred_at,
                (Shift.ended_at.is_(None) | (F.occurred_at < Shift.ended_at)))


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


async def attribution(session, broadcast_id):
    broadcast = await session.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise HTTPException(404, 'LIVE no encontrado')
    stop = broadcast.ended_at or datetime.now(timezone.utc)
    shifts = (await session.scalars(select(Shift).where(
        Shift.account_id == broadcast.account_id, Shift.started_at < stop,
        (Shift.ended_at.is_(None) | (Shift.ended_at > broadcast.started_at)))
        .order_by(Shift.started_at))).all()
    result = []
    cursor = broadcast.started_at
    for shift in shifts:
        start = max(shift.started_at, broadcast.started_at)
        end = min(shift.ended_at or stop, stop)
        if start > cursor:
            result.append({'user_id': None, 'start': cursor, 'end': start})
        result.append({'shift_id': shift.id, 'user_id': shift.user_id, 'start': start, 'end': end})
        cursor = max(cursor, end)
    if cursor < stop:
        result.append({'user_id': None, 'start': cursor, 'end': stop})
    grouped = (await session.execute(select(Shift.user_id, *aggregates()).select_from(F)
        .outerjoin(Shift, shift_join()).where(F.broadcast_id == broadcast_id)
        .group_by(Shift.user_id))).mappings().all()
    return {'broadcast_id': broadcast_id, 'intervals': result, 'by_user': [dict(r) for r in grouped]}
