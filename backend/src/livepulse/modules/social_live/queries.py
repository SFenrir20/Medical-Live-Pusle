"""Read models for Medical 360. Dashboards read consolidated live_metrics and captured_phones,
never raw comments. Aggregation is done on bounded, already-filtered row sets in Python so the
same code runs on PostgreSQL and in portable tests."""
from datetime import timedelta
from statistics import median

from fastapi import HTTPException
from sqlalchemy import select

from ...shared.config import settings
from .models import CapturedPhone, Live, LiveComment, LiveMetrics, TiktokAccount, Tiktoker
from .schemas import LIMA
from .service import aware_utc, contact_time_seconds, utcnow

BUCKETS = (('lt_5_min', 0, 300), ('5_to_15_min', 300, 900), ('15_to_30_min', 900, 1800),
           ('gt_30_min', 1800, None))
METRIC_FIELDS = ('views', 'unique_viewers', 'comments_count', 'likes_count', 'shares_count',
                 'new_followers', 'donations_count', 'direct_messages_count',
                 'interested_viewers', 'phones_captured')


def iso(value):
    return aware_utc(value).isoformat() if value is not None else None


def lima_iso(value):
    return aware_utc(value).astimezone(LIMA).isoformat() if value is not None else None


def live_filters(query, date_from=None, date_to=None, tiktoker_id=None, account_id=None,
                 status=None):
    if date_from is not None:
        query = query.where(Live.started_at >= date_from)
    if date_to is not None:
        query = query.where(Live.started_at < date_to)
    if tiktoker_id:
        query = query.where(Live.tiktoker_id == tiktoker_id)
    if account_id:
        query = query.where(Live.account_id == account_id)
    if status:
        query = query.where(Live.status == status)
    return query


def seconds_of(live: Live) -> float:
    if live.status in ('scheduled', 'cancelled'):
        return 0.0
    if live.duration_seconds is not None:
        return float(live.duration_seconds)
    return max(0.0, (utcnow() - aware_utc(live.started_at)).total_seconds())


def rate(count, seconds):
    return round(count / (max(seconds, 60.0) / 3600), 2) if seconds > 0 else 0.0


def metrics_dict(m: LiveMetrics | None) -> dict:
    if m is None:
        return {**{f: 0 for f in METRIC_FIELDS}, 'leads_per_hour': 0.0}
    return {**{f: getattr(m, f) for f in METRIC_FIELDS}, 'leads_per_hour': m.leads_per_hour}


def live_summary(live, metrics, tiktoker=None, account=None) -> dict:
    return {'id': live.id, 'status': live.status,
            'tiktoker_id': live.tiktoker_id, 'tiktoker': tiktoker.name if tiktoker else None,
            'account_id': live.account_id,
            'account': ('@' + account.username) if account else None,
            'started_at': iso(live.started_at), 'started_at_lima': lima_iso(live.started_at),
            'ended_at': iso(live.ended_at), 'ended_at_lima': lima_iso(live.ended_at),
            'duration_seconds': live.duration_seconds, 'metrics': metrics_dict(metrics)}


async def _rows(session, **filters):
    query = (select(Live, LiveMetrics, Tiktoker, TiktokAccount)
             .join(Tiktoker, Tiktoker.id == Live.tiktoker_id)
             .join(TiktokAccount, TiktokAccount.id == Live.account_id)
             .outerjoin(LiveMetrics, LiveMetrics.live_id == Live.id)
             .order_by(Live.started_at.desc(), Live.id))
    return query, live_filters(query, **filters)


async def overview(session, **filters):
    _, query = await _rows(session, **filters)
    rows = (await session.execute(query.limit(20000))).all()
    total = {f: 0 for f in METRIC_FIELDS}
    seconds = 0.0
    for live, metrics, _, _ in rows:
        seconds += seconds_of(live)
        for f in METRIC_FIELDS:
            total[f] += getattr(metrics, f) if metrics else 0
    return {'lives': len(rows), 'live_now': sum(1 for r in rows if r[0].status == 'live'),
            'views': total['views'], 'unique_viewers': total['unique_viewers'],
            'comments': total['comments_count'], 'likes': total['likes_count'],
            'shares': total['shares_count'], 'followers': total['new_followers'],
            'interested': total['interested_viewers'], 'donations': total['donations_count'],
            'direct_messages': total['direct_messages_count'],
            'phones': total['phones_captured'], 'live_hours': round(seconds / 3600, 2),
            'leads_per_hour': rate(total['phones_captured'], seconds),
            'note': 'unique_viewers suma el máximo reportado por cada live; un mismo usuario '
                    'en dos lives se cuenta dos veces.'}


async def list_lives(session, limit, offset, **filters):
    _, query = await _rows(session, **filters)
    rows = (await session.execute(query.offset(offset).limit(limit + 1))).all()
    return {'items': [live_summary(live, metrics, tiktoker, account)
                      for live, metrics, tiktoker, account in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}


async def comments_state(session, live: Live) -> str:
    """available | purged | none"""
    has = await session.scalar(select(LiveComment.id).where(LiveComment.live_id == live.id).limit(1))
    if has is not None:
        return 'available'
    metrics = await session.scalar(select(LiveMetrics).where(LiveMetrics.live_id == live.id))
    cutoff = utcnow() - timedelta(days=settings.comments_retention_days)
    reference = live.ended_at or live.started_at
    if metrics and metrics.comments_count > 0 and aware_utc(reference) < cutoff:
        return 'purged'
    return 'none'


async def live_detail(session, live: Live):
    metrics = await session.scalar(select(LiveMetrics).where(LiveMetrics.live_id == live.id))
    tiktoker = await session.get(Tiktoker, live.tiktoker_id)
    account = await session.get(TiktokAccount, live.account_id)
    phones = (await session.scalars(select(CapturedPhone).where(
        CapturedPhone.live_id == live.id))).all()
    times = [t for t in (contact_time_seconds(p) for p in phones) if t is not None]
    return {**live_summary(live, metrics, tiktoker, account),
            'comments_available': await comments_state(session, live) != 'purged',
            'comments_retention_days': settings.comments_retention_days,
            'phones': {'total': len(phones),
                       'new': sum(p.status == 'new' for p in phones),
                       'contacted': sum(p.status == 'contacted' for p in phones),
                       'qualified': sum(p.status == 'qualified' for p in phones),
                       'discarded': sum(p.status == 'discarded' for p in phones),
                       'avg_contact_seconds': round(sum(times) / len(times), 1) if times else None}}


def retention_error():
    return HTTPException(410, {
        'code': 'COMMENTS_RETENTION_EXPIRED',
        'message': 'Los comentarios detallados de este Live ya no están disponibles. '
                   'Las métricas históricas permanecen disponibles.'})


async def live_comments(session, live: Live, limit, offset):
    if await comments_state(session, live) == 'purged':
        raise retention_error()
    rows = (await session.scalars(select(LiveComment).where(LiveComment.live_id == live.id)
            .order_by(LiveComment.created_at, LiveComment.id).offset(offset)
            .limit(limit + 1))).all()
    return {'items': [{'id': r.id, 'username': r.username, 'comment': r.comment,
                       'phone_detected': r.phone_detected, 'interested': r.interested,
                       'created_at': iso(r.created_at), 'created_at_lima': lima_iso(r.created_at)}
                      for r in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}


def phone_dict(p: CapturedPhone) -> dict:
    return {'id': p.id, 'live_id': p.live_id, 'phone': p.phone,
            'tiktok_username': p.tiktok_username, 'source': p.source, 'status': p.status,
            'advisor_id': p.advisor_id,
            'captured_at': iso(p.captured_at), 'captured_at_lima': lima_iso(p.captured_at),
            'contacted_at': iso(p.contacted_at), 'contacted_at_lima': lima_iso(p.contacted_at),
            'contact_time_seconds': contact_time_seconds(p)}


async def live_phones(session, live: Live, status, limit, offset):
    query = select(CapturedPhone).where(CapturedPhone.live_id == live.id)
    if status:
        query = query.where(CapturedPhone.status == status)
    rows = (await session.scalars(query.order_by(CapturedPhone.captured_at, CapturedPhone.id)
            .offset(offset).limit(limit + 1))).all()
    return {'items': [phone_dict(r) for r in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}


async def _phone_status_by(session, key, **filters):
    """key: Live column to group by. Returns {key: {phones, contacted, qualified}}."""
    query = select(key, CapturedPhone.status, CapturedPhone.contacted_at,
                   CapturedPhone.captured_at).join(Live, Live.id == CapturedPhone.live_id)
    out: dict = {}
    for k, status, contacted_at, captured_at in (await session.execute(
            live_filters(query, **filters))).all():
        row = out.setdefault(k, {'phones': 0, 'contacted': 0, 'qualified': 0, 'seconds': []})
        row['phones'] += 1
        row['contacted'] += contacted_at is not None
        row['qualified'] += status == 'qualified'
        if contacted_at is not None:
            row['seconds'].append(max(0, (aware_utc(contacted_at)
                                          - aware_utc(captured_at)).total_seconds()))
    return out


SORTS = {'phones': 'phones', 'leads_per_hour': 'leads_per_hour', 'views': 'views',
         'interested': 'interested', 'conversion': 'conversion'}


async def ranking(session, sort_by, **filters):
    _, query = await _rows(session, **filters)
    rows = (await session.execute(query.limit(20000))).all()
    status = await _phone_status_by(session, Live.tiktoker_id, **filters)
    board: dict = {}
    for live, metrics, tiktoker, _ in rows:
        r = board.setdefault(tiktoker.id, {
            'tiktoker_id': tiktoker.id, 'tiktoker': tiktoker.name, 'lives': 0, 'views': 0,
            'interested': 0, 'comments': 0, 'seconds': 0.0})
        r['lives'] += 1
        r['seconds'] += seconds_of(live)
        if metrics:
            r['views'] += metrics.views
            r['interested'] += metrics.interested_viewers
            r['comments'] += metrics.comments_count
    items = []
    for tid, r in board.items():
        s = status.get(tid, {'phones': 0, 'contacted': 0, 'qualified': 0})
        items.append({
            'tiktoker_id': tid, 'tiktoker': r['tiktoker'], 'lives': r['lives'],
            'live_hours': round(r['seconds'] / 3600, 2), 'views': r['views'],
            'interested': r['interested'], 'comments': r['comments'],
            'phones': s['phones'], 'contacted': s['contacted'], 'qualified': s['qualified'],
            'leads_per_hour': rate(s['phones'], r['seconds']),
            # conversion = phones that reached "qualified" / phones captured.
            'conversion': round(s['qualified'] / s['phones'], 4) if s['phones'] else 0.0})
    items.sort(key=lambda i: (i[SORTS[sort_by]], i['phones']), reverse=True)
    for position, item in enumerate(items, 1):
        item['rank'] = position
    return {'sort_by': sort_by, 'items': items}


async def accounts_performance(session, **filters):
    _, query = await _rows(session, **filters)
    rows = (await session.execute(query.limit(20000))).all()
    status = await _phone_status_by(session, Live.account_id, **filters)
    board: dict = {}
    for live, metrics, _, account in rows:
        r = board.setdefault(account.id, {
            'account_id': account.id, 'account': '@' + account.username, 'name': account.name,
            'type': account.type, 'lives': 0, 'views': 0, 'comments': 0, 'likes': 0,
            'interested': 0, 'donations': 0, 'seconds': 0.0})
        r['lives'] += 1
        r['seconds'] += seconds_of(live)
        if metrics:
            r['views'] += metrics.views
            r['comments'] += metrics.comments_count
            r['likes'] += metrics.likes_count
            r['interested'] += metrics.interested_viewers
            r['donations'] += metrics.donations_count
    items = []
    for aid, r in board.items():
        s = status.get(aid, {'phones': 0, 'contacted': 0, 'qualified': 0})
        seconds = r.pop('seconds')
        items.append({**r, 'live_hours': round(seconds / 3600, 2), 'phones': s['phones'],
                      'contacted': s['contacted'], 'qualified': s['qualified'],
                      'leads_per_hour': rate(s['phones'], seconds)})
    items.sort(key=lambda i: i['phones'], reverse=True)
    return {'items': items}


async def _phone_rows(session, date_from, date_to, tiktoker_id, account_id):
    query = select(CapturedPhone.captured_at, CapturedPhone.live_id).join(
        Live, Live.id == CapturedPhone.live_id)
    if date_from is not None:
        query = query.where(CapturedPhone.captured_at >= date_from)
    if date_to is not None:
        query = query.where(CapturedPhone.captured_at < date_to)
    if tiktoker_id:
        query = query.where(Live.tiktoker_id == tiktoker_id)
    if account_id:
        query = query.where(Live.account_id == account_id)
    return (await session.execute(query.limit(200000))).all()


def bucket_key(moment, granularity):
    local = aware_utc(moment).astimezone(LIMA)
    if granularity == 'hour_of_day':
        return local.hour
    if granularity == 'day':
        return local.date().isoformat()
    if granularity == 'week':
        start = local.date() - timedelta(days=local.weekday())
        return start.isoformat()
    return local.strftime('%Y-%m')


async def hourly(session, granularity, date_from, date_to, tiktoker_id, account_id):
    rows = await _phone_rows(session, date_from, date_to, tiktoker_id, account_id)
    counts: dict = {}
    for captured_at, _ in rows:
        key = bucket_key(captured_at, granularity)
        counts[key] = counts.get(key, 0) + 1
    result: dict = {'granularity': granularity, 'timezone': 'America/Lima', 'total': len(rows)}
    if granularity != 'hour_of_day':
        result['items'] = [{'period': k, 'phones': v} for k, v in sorted(counts.items())]
        return result
    # Hours when at least one live was on air: a quiet 3 AM is not the "worst" hour.
    lq = live_filters(select(Live), date_from, date_to, tiktoker_id, account_id)
    active: set[int] = set()
    for live in (await session.scalars(lq.limit(20000))).all():
        start = aware_utc(live.started_at).astimezone(LIMA)
        end = aware_utc(live.ended_at or utcnow()).astimezone(LIMA)
        cursor = start.replace(minute=0, second=0, microsecond=0)
        while cursor <= end:
            active.add(cursor.hour)
            cursor += timedelta(hours=1)
    items = [{'hour': h, 'label': f'{h:02d}:00', 'phones': counts.get(h, 0),
              'live_active': h in active or h in counts} for h in range(24)]
    candidates = [i for i in items if i['live_active']]
    result['items'] = items
    result['best_hour'] = max(candidates, key=lambda i: i['phones'])['hour'] \
        if candidates and result['total'] else None
    result['worst_hour'] = min(candidates, key=lambda i: i['phones'])['hour'] \
        if candidates and result['total'] else None
    return result


async def contact_performance(session, date_from, date_to, tiktoker_id, account_id):
    query = select(CapturedPhone.captured_at, CapturedPhone.contacted_at, CapturedPhone.status
                   ).join(Live, Live.id == CapturedPhone.live_id)
    if date_from is not None:
        query = query.where(CapturedPhone.captured_at >= date_from)
    if date_to is not None:
        query = query.where(CapturedPhone.captured_at < date_to)
    if tiktoker_id:
        query = query.where(Live.tiktoker_id == tiktoker_id)
    if account_id:
        query = query.where(Live.account_id == account_id)
    rows = (await session.execute(query.limit(200000))).all()
    seconds = sorted(max(0.0, (aware_utc(c) - aware_utc(a)).total_seconds())
                     for a, c, _ in rows if c is not None)
    pending = sum(1 for _, c, s in rows if c is None and s == 'new')
    pct = {}
    for name, low, high in BUCKETS:
        n = sum(1 for s in seconds if s >= low and (high is None or s < high))
        pct[name] = round(100 * n / len(seconds), 1) if seconds else 0.0
    return {'phones': len(rows), 'contacted': len(seconds), 'uncontacted': pending,
            'average_seconds': round(sum(seconds) / len(seconds), 1) if seconds else None,
            'median_seconds': round(median(seconds), 1) if seconds else None,
            'min_seconds': seconds[0] if seconds else None,
            'max_seconds': seconds[-1] if seconds else None,
            'percent': pct, 'percent_base': 'phones contacted'}
