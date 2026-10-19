"""Ranking of fans: who comments, likes, gives gifts or stays around the most.

Only for the people who run the business (supervisor, marketing head, manager): permission
`audience:read`. It never shows phone numbers, only whether the user left one.

Per live and per user we keep counters (audience_members). They are filled by the same ingestion
that feeds the metrics (so each event counts once) and purged with the comments.

What the numbers are, and are not:
  * comments, likes, shares, gifts, diamonds, follows: exact, as TikTok reported them.
  * "presence": minutes between the first and the last time the user showed up in an event.
    TikTok never says who leaves, and a silent viewer produces no event, so it is an estimate
    of the time watching, only for people who interacted."""
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select, text, update
from sqlalchemy.exc import IntegrityError

from ...shared.config import settings
from ...shared.db import get_session
from . import queries
from .models import AudienceMember, CapturedPhone, Live
from .security import require_scope
from .service import aware_utc, utcnow

router = APIRouter(prefix='/api/audience', tags=['audience'])
viewer = require_scope('audience:read')

Sort = Literal['diamonds', 'comments', 'likes', 'shares', 'presence', 'lives']
COUNTERS = ('comments', 'likes', 'shares', 'gifts', 'diamonds', 'follows', 'joins')


def user_key(name) -> str | None:
    """The same person written '@Ana', 'ana ' or 'ANA' is one user."""
    key = (name or '').strip().lstrip('@').strip().lower()[:128]
    return key or None


def contribution(event) -> dict[str, int]:
    """Counters an ingestion event adds to its user. {} = it does not belong in the ranking."""
    kind = event.event_type
    if kind == 'comment':
        return {'comments': 1}
    if kind == 'like':
        return {'likes': max(1, event.value)}
    if kind == 'share':
        return {'shares': 1}
    if kind == 'follow':
        return {'follows': 1}
    if kind == 'view':
        return {'joins': 1}
    if kind == 'donation':
        return {'gifts': max(1, event.value), 'diamonds': event.diamonds}
    return {}


async def record(session, live_id: str, username, display_name, at, counters: dict[str, int]):
    """Add `counters` to the user's row of this live, creating it the first time. The update
    comes first so the common case is one statement; a concurrent insert falls back to it."""
    key = user_key(username)
    if key is None or not counters:
        return
    at = aware_utc(at)

    def bump():
        values = {name: getattr(AudienceMember, name) + counters.get(name, 0)
                  for name in COUNTERS if counters.get(name)}
        values['first_seen_at'] = case((AudienceMember.first_seen_at > at, at),
                                       else_=AudienceMember.first_seen_at)
        values['last_seen_at'] = case((AudienceMember.last_seen_at < at, at),
                                      else_=AudienceMember.last_seen_at)
        if display_name:
            values['display_name'] = display_name[:128]
        return (update(AudienceMember).where(AudienceMember.live_id == live_id,
                                             AudienceMember.user_key == key).values(**values))

    if (await session.execute(bump())).rowcount:
        return
    try:
        async with session.begin_nested():
            session.add(AudienceMember(
                live_id=live_id, user_key=key, username=username.strip().lstrip('@')[:128],
                display_name=(display_name or None) and display_name[:128],
                first_seen_at=at, last_seen_at=at,
                **{name: counters.get(name, 0) for name in COUNTERS}))
            await session.flush()
    except IntegrityError:
        await session.execute(bump())  # another worker created it first


def _seconds_between(session, start, end):
    """Seconds from start to end, written for the database in use."""
    if session.get_bind().dialect.name == 'sqlite':
        return (func.julianday(end) - func.julianday(start)) * 86400
    return func.extract('epoch', end - start)


SORT_COLUMNS = {'diamonds': 'diamonds', 'comments': 'comments', 'likes': 'likes',
                'shares': 'shares', 'presence': 'presence_seconds', 'lives': 'lives'}


async def ranking(session, *, live_id: str | None, days: int, sort: str, limit: int) -> dict:
    """Top users of one live, or accumulated over the last `days` days across all lives."""
    seconds = _seconds_between(session, AudienceMember.first_seen_at, AudienceMember.last_seen_at)
    totals = {name: func.sum(getattr(AudienceMember, name)).label(name) for name in COUNTERS}
    measures = {**totals, 'lives': func.count(func.distinct(AudienceMember.live_id)).label('lives'),
                'presence_seconds': func.sum(seconds).label('presence_seconds')}
    query = (select(AudienceMember.user_key, func.max(AudienceMember.username).label('username'),
                    func.max(AudienceMember.display_name).label('display_name'),
                    func.min(AudienceMember.first_seen_at).label('first_seen_at'),
                    func.max(AudienceMember.last_seen_at).label('last_seen_at'),
                    *measures.values())
             .group_by(AudienceMember.user_key))
    since = None
    if live_id:
        query = query.where(AudienceMember.live_id == live_id)
    else:
        since = utcnow() - timedelta(days=days)
        query = query.where(AudienceMember.last_seen_at >= since)
    chosen = SORT_COLUMNS[sort]
    order = [measures[chosen].desc()]
    order += [measures[name].desc() for name in ('diamonds', 'comments', 'likes')
              if name != chosen]
    members = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.execute(query.order_by(*order, AudienceMember.user_key)
                                  .limit(limit))).all()

    keys = {row.user_key for row in rows}
    left_contact: set[str] = set()
    if keys:
        # Only whether she left a number (never the number): matched by TikTok user name.
        names = (await session.scalars(select(func.lower(CapturedPhone.tiktok_username)).where(
            func.lower(CapturedPhone.tiktok_username).in_(keys | {'@' + k for k in keys})))).all()
        left_contact = {user_key(n) for n in names}
    items = [{
        'user': row.username, 'name': row.display_name, 'user_key': row.user_key,
        'comments': int(row.comments), 'likes': int(row.likes), 'shares': int(row.shares),
        'gifts': int(row.gifts), 'diamonds': int(row.diamonds), 'follows': int(row.follows),
        'followed': row.follows > 0, 'lives': int(row.lives), 'presence_seconds': max(0, round(float(row.presence_seconds or 0))),
        'first_seen_at': queries.iso(aware_utc(row.first_seen_at)),
        'last_seen_at': queries.iso(aware_utc(row.last_seen_at)),
        'left_contact': row.user_key in left_contact} for row in rows]
    return {'scope': 'live' if live_id else 'period', 'live_id': live_id,
            'days': None if live_id else days,
            'since': queries.iso(since) if since else None, 'sort': sort,
            'members': members, 'items': items,
            'retention_days': settings.comments_retention_days,
            'note': 'El tiempo es una estimación: TikTok no informa cuándo sale cada persona y '
                    'quien mira en silencio no genera eventos.'}


@router.get('/top')
async def top(live_id: str | None = Query(None, min_length=1, max_length=40),
              days: int = Query(30, ge=1, le=90),
              sort: Sort = 'diamonds', limit: int = Query(20, ge=1, le=100),
              who=Depends(viewer), session=Depends(get_session)):
    """Fans ranking. With `live_id`: that live. Without: accumulated over `days` (recurring
    fans have lives > 1). Phones are never returned."""
    if live_id and await session.get(Live, live_id) is None:
        raise HTTPException(404, 'Live no encontrado.')
    return await ranking(session, live_id=live_id, days=days, sort=sort, limit=limit)


# ---- history already stored in raw_events (migration 0011) -------------------------------

BACKFILL_KINDS = {'comment': 'comments', 'like': 'likes', 'share': 'shares',
                  'follow': 'follows', 'join': 'joins', 'gift': 'gifts'}


def _int(value, default=0):
    try:
        return max(0, min(int(value), 2_000_000_000))
    except (TypeError, ValueError):
        return default


def _moment(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware_utc(datetime.fromisoformat(str(value)))


def backfill_from_raw_events(conn, days: int | None = None) -> int:
    """Rebuild the counters of the last `days` days from raw_events, so the ranking has data
    for the lives that already happened. Same rules as live ingestion (the final tick of a gift
    streak, ids without '@'). Replaces whatever the table held for those lives: run it once on
    an empty table. Returns the number of user rows written."""
    days = settings.comments_retention_days if days is None else days
    cutoff = utcnow() - timedelta(days=days)
    live_ids = {row[0] for row in conn.execute(text('SELECT id FROM lives'))}
    rows: dict[tuple[str, str], dict] = {}
    cursor = conn.execute(text(
        'SELECT broadcast_id, type, occurred_at, payload FROM raw_events '
        "WHERE broadcast_id IS NOT NULL AND type IN ('comment','like','share','follow','join',"
        "'gift') ORDER BY occurred_at"))
    for broadcast_id, kind, occurred_at, payload in cursor:
        live_id = f'TT-{broadcast_id}'
        at = _moment(occurred_at)
        if live_id not in live_ids or at < cutoff:
            continue
        if isinstance(payload, str):
            payload = json.loads(payload or '{}')
        payload = payload or {}
        name = str(payload.get('username') or payload.get('nickname')
                   or payload.get('user') or '').strip()[:128]
        key = user_key(name)
        if key is None:
            continue
        add = {BACKFILL_KINDS[kind]: 1}
        if kind == 'like':
            add = {'likes': max(1, _int(payload.get('count'), 1))}
        elif kind == 'gift':
            final = _int(payload.get('gift_type')) != 1 or _int(payload.get('repeat_end')) == 1
            if not final:
                continue
            quantity = max(1, _int(payload.get('repeat_count'), 1))
            add = {'gifts': quantity, 'diamonds': _int(payload.get('diamond_count')) * quantity}
        row = rows.setdefault((live_id, key), {
            'live_id': live_id, 'user_key': key, 'username': name.lstrip('@'),
            'display_name': None, 'first_seen_at': at, 'last_seen_at': at,
            **{c: 0 for c in COUNTERS}})
        row['first_seen_at'], row['last_seen_at'] = min(row['first_seen_at'], at), max(
            row['last_seen_at'], at)
        row['display_name'] = (payload.get('nickname') or row['display_name'])
        for column, amount in add.items():
            row[column] += amount
    conn.execute(text('DELETE FROM audience_members'))
    for row in rows.values():
        row['display_name'] = (row['display_name'] or None) and str(row['display_name'])[:128]
        conn.execute(text(
            'INSERT INTO audience_members (live_id, user_key, username, display_name, '
            'first_seen_at, last_seen_at, comments, likes, shares, gifts, diamonds, follows, '
            'joins) VALUES (:live_id, :user_key, :username, :display_name, :first_seen_at, '
            ':last_seen_at, :comments, :likes, :shares, :gifts, :diamonds, :follows, :joins)'),
            row)
    return len(rows)
