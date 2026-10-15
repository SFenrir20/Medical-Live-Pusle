"""Read models for Medical 360 and the Social Pulse dashboards.

Dashboards read consolidated live_metrics and the contact registry, never raw comments. Counting
and attribution run on bounded, already-filtered row sets in Python so the same code runs on
PostgreSQL and in portable tests.

Three things are kept apart (a live is NOT owned by one TikToker):
- the broadcast: account and real time window (lives);
- the shifts: who worked and during which interval (shifts);
- the attribution: who a contact or metric belongs to is decided by time, with an explicit
  "Sin asignar" when nobody had a shift. lives.tiktoker_id is only a fallback.

Phone metrics are per CONTACT and use the date of its FIRST capture (Lima calendar):
a number that reappears in another live or account is never counted again."""
from collections import defaultdict
from datetime import timedelta
from statistics import median
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from ...shared.config import settings
from ..analytics.models import MonitorState, UserRole
from ..shifts.models import Shift
from .models import (
    CapturedPhone,
    Live,
    LiveComment,
    LiveMetrics,
    PhoneRegistry,
    TiktokAccount,
    Tiktoker,
)
from .schemas import LIMA
from .service import aware_utc, contact_time_seconds, utcnow

BUCKETS = (('lt_5_min', 0, 300), ('5_to_15_min', 300, 900), ('15_to_30_min', 900, 1800),
           ('gt_30_min', 1800, None))
METRIC_FIELDS = ('views', 'comments_count', 'likes_count', 'shares_count', 'new_followers',
                 'donations_count', 'direct_messages_count', 'interested_viewers',
                 'phones_captured', 'phone_mentions')
ALLOCATED = ('views', 'interested_viewers', 'comments_count', 'likes_count', 'shares_count',
             'new_followers', 'donations_count')
UNASSIGNED = 'Sin asignar'
ROW_CAP = 20000
STATE_LABEL = {'new': 'Por contactar', 'contacted': 'Contactado', 'qualified': 'Calificado',
               'discarded': 'Descartado'}


def iso(value):
    return aware_utc(value).isoformat() if value is not None else None


def lima_iso(value):
    return aware_utc(value).astimezone(LIMA).isoformat() if value is not None else None


def stamp(value):
    return {'utc': iso(value), 'lima': lima_iso(value)}


def seconds_of(live: Live) -> float:
    if live.status in ('scheduled', 'cancelled'):
        return 0.0
    if live.duration_seconds is not None:
        return float(live.duration_seconds)
    return max(0.0, (utcnow() - aware_utc(live.started_at)).total_seconds())


def live_end(live: Live):
    return aware_utc(live.ended_at) if live.ended_at else utcnow()


def rate(count, seconds):
    return round(count / (max(seconds, 60.0) / 3600), 2) if seconds > 0 else 0.0


def metrics_dict(m: LiveMetrics | None) -> dict:
    """Every figure either has a connected source or is explicitly unavailable (None)."""
    base = {f: 0 for f in METRIC_FIELDS}
    base.update(leads_per_hour=0.0, peak_viewers=0, average_viewers=None, unique_viewers=None)
    if m is not None:
        base.update({f: getattr(m, f) for f in METRIC_FIELDS})
        base.update(leads_per_hour=m.leads_per_hour, peak_viewers=m.peak_viewers,
                    average_viewers=(round(m.viewer_sum / m.viewer_samples, 1)
                                     if m.viewer_samples else None),
                    unique_viewers=m.unique_viewers)
    # What the sender reported is not evidence that private messages are being captured.
    base['direct_messages_reported'] = base.pop('direct_messages_count')
    base['direct_messages_capture'] = settings.dm_capture_connected
    base['audience_note'] = ('peak_viewers y average_viewers son espectadores simultáneos '
                             'observados; unique_viewers es null cuando no hay fuente.')
    return base


# ---------- attribution by shift ----------

class Attribution:
    """Who was in charge of an account at a given moment."""

    def __init__(self, shifts, names, tiktokers):
        self._names, self._tiktokers = names, tiktokers
        self._by_account: dict[str, list] = defaultdict(list)
        for s in shifts:
            self._by_account[s.account_id].append((
                aware_utc(s.started_at), aware_utc(s.ended_at) if s.ended_at else None,
                s.user_id, s.display_name or names.get(s.user_id) or s.user_id))
        for rows in self._by_account.values():
            rows.sort(key=lambda r: r[0])

    def name_of(self, ident):
        if ident is None:
            return UNASSIGNED
        return self._names.get(ident) or self._tiktokers.get(ident) or ident

    def at(self, account_id, moment, fallback_id=None):
        moment = aware_utc(moment)
        for start, end, uid, name in self._by_account.get(account_id, ()):
            if start <= moment and (end is None or moment < end):
                return uid, name
        if fallback_id:
            return fallback_id, self.name_of(fallback_id)
        return None, UNASSIGNED

    def intervals(self, live: Live):
        """Consecutive [start, end) pieces of the broadcast with who covered each one."""
        start, stop = aware_utc(live.started_at), live_end(live)
        pieces, cursor = [], start
        for s_start, s_end, uid, name in self._by_account.get(live.account_id, ()):
            end = s_end or stop
            if end <= cursor or s_start >= stop:
                continue
            piece_start = max(s_start, cursor)
            if piece_start > cursor:
                pieces.append((cursor, piece_start, None, UNASSIGNED))
            pieces.append((piece_start, min(end, stop), uid, name))
            cursor = min(end, stop)
        if cursor < stop:
            pieces.append((cursor, stop, None, UNASSIGNED))
        if live.tiktoker_id:  # an explicit assignment only fills the holes
            fb = live.tiktoker_id
            pieces = [(a, b, fb, self.name_of(fb)) if uid is None else (a, b, uid, name)
                      for a, b, uid, name in pieces]
        return pieces

    def shares(self, live: Live) -> dict:
        """{id|None: (name, fraction)} summing to 1 over the broadcast."""
        pieces = self.intervals(live)
        total = sum((b - a).total_seconds() for a, b, _, _ in pieces) or 1.0
        out: dict = {}
        for a, b, uid, name in pieces:
            _, frac = out.get(uid, (name, 0.0))
            out[uid] = (name, frac + (b - a).total_seconds() / total)
        if not out:
            out[live.tiktoker_id] = (self.name_of(live.tiktoker_id), 1.0)
        return out


def window_of(lives):
    items = list(lives)
    start = min(aware_utc(i.started_at) for i in items)
    stop = max(aware_utc(i.ended_at) if i.ended_at else utcnow() for i in items)
    return start, stop


async def load_attribution(session, lives) -> Attribution:
    """`lives` may be Live rows or anything with account_id/started_at/ended_at."""
    tiktokers = {t.id: t.name for t in (await session.scalars(select(Tiktoker))).all()}
    lives = [row for row in lives if row.account_id]
    if not lives:
        return Attribution([], {}, tiktokers)
    accounts = {row.account_id for row in lives}
    start, stop = window_of(lives)
    shifts = (await session.scalars(select(Shift).where(
        Shift.account_id.in_(accounts), Shift.started_at < stop + timedelta(seconds=1),
        or_(Shift.ended_at.is_(None), Shift.ended_at > start)))).all()
    ids = {s.user_id for s in shifts}
    names = {}
    if ids:
        names = {r.user_id: r.display_name for r in (await session.scalars(
            select(UserRole).where(UserRole.user_id.in_(ids)))).all() if r.display_name}
    return Attribution(shifts, names, tiktokers)


def involves(shares, tiktoker_id) -> bool:
    return tiktoker_id is None or tiktoker_id in shares


# ---------- lives ----------

def date_filters(query, date_from=None, date_to=None, account_id=None, status=None):
    if date_from is not None:
        query = query.where(Live.started_at >= date_from)
    if date_to is not None:
        query = query.where(Live.started_at < date_to)
    if account_id:
        query = query.where(Live.account_id == account_id)
    if status:
        query = query.where(Live.status == status)
    return query


async def fetch_lives(session, date_from=None, date_to=None, account_id=None, status=None):
    query = (select(Live, LiveMetrics, TiktokAccount)
             .join(TiktokAccount, TiktokAccount.id == Live.account_id)
             .outerjoin(LiveMetrics, LiveMetrics.live_id == Live.id)
             .order_by(Live.started_at.desc(), Live.id).limit(ROW_CAP))
    return (await session.execute(date_filters(query, date_from, date_to, account_id, status))).all()


def live_summary(live, metrics, account, shares) -> dict:
    staff = [{'id': k, 'name': name, 'share': round(frac, 4)}
             for k, (name, frac) in sorted(shares.items(), key=lambda kv: -kv[1][1])]
    assigned = [s for s in staff if s['id'] is not None]
    primary = assigned[0] if assigned else {'id': None, 'name': UNASSIGNED}
    return {'id': live.id, 'status': live.status,
            'tiktoker_id': primary['id'], 'tiktoker': primary['name'], 'tiktokers': staff,
            'account_id': live.account_id,
            'account': ('@' + account.username) if account else None,
            'started_at': iso(live.started_at), 'started_at_lima': lima_iso(live.started_at),
            'ended_at': iso(live.ended_at), 'ended_at_lima': lima_iso(live.ended_at),
            'duration_seconds': live.duration_seconds, 'metrics': metrics_dict(metrics)}


async def list_lives(session, limit, offset, tiktoker_id=None, **filters):
    rows = await fetch_lives(session, **filters)
    attribution = await load_attribution(session, [r[0] for r in rows])
    kept = []
    for live, metrics, account in rows:
        shares = attribution.shares(live)
        if involves(shares, tiktoker_id):
            kept.append(live_summary(live, metrics, account, shares))
    page = kept[offset:offset + limit + 1]
    return {'items': page[:limit], 'next_offset': offset + limit if len(page) > limit else None}


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


async def live_phone_rows(session, live: Live, status=None):
    """Appearances of contacts in this live, with the contact's attention state."""
    query = (select(CapturedPhone, PhoneRegistry)
             .join(PhoneRegistry, PhoneRegistry.phone == CapturedPhone.phone)
             .where(CapturedPhone.live_id == live.id))
    if status:
        query = query.where(PhoneRegistry.status == status)
    return (await session.execute(
        query.order_by(CapturedPhone.captured_at, CapturedPhone.id))).all()


async def live_detail(session, live: Live):
    metrics = await session.scalar(select(LiveMetrics).where(LiveMetrics.live_id == live.id))
    account = await session.get(TiktokAccount, live.account_id)
    attribution = await load_attribution(session, [live])
    rows = await live_phone_rows(session, live)
    firsts = [reg for app, reg in rows if app.is_new]
    times = [t for t in (contact_time_seconds(reg) for reg in firsts) if t is not None]
    return {**live_summary(live, metrics, account, attribution.shares(live)),
            'intervals': [{'start': iso(a), 'end': iso(b), 'tiktoker_id': uid, 'tiktoker': name}
                          for a, b, uid, name in attribution.intervals(live)],
            'comments_available': await comments_state(session, live) != 'purged',
            'comments_retention_days': settings.comments_retention_days,
            'phones': {'total': len(firsts), 'mentions': len(rows),
                       'new': sum(r.status == 'new' for r in firsts),
                       'contacted': sum(r.status == 'contacted' for r in firsts),
                       'qualified': sum(r.status == 'qualified' for r in firsts),
                       'discarded': sum(r.status == 'discarded' for r in firsts),
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


def phone_dict(appearance: CapturedPhone, registry: PhoneRegistry) -> dict:
    return {'id': registry.id, 'live_id': appearance.live_id, 'phone': registry.phone,
            'is_new': appearance.is_new, 'tiktok_username': appearance.tiktok_username,
            'source': appearance.source, 'status': registry.status,
            'advisor_id': registry.advisor_id,
            'captured_at': iso(appearance.captured_at),
            'captured_at_lima': lima_iso(appearance.captured_at),
            'first_captured_at': iso(registry.first_captured_at),
            'contacted_at': iso(registry.contacted_at),
            'contacted_at_lima': lima_iso(registry.contacted_at),
            'contact_time_seconds': contact_time_seconds(registry)}


async def live_phones(session, live: Live, status, limit, offset):
    rows = await live_phone_rows(session, live, status)
    page = rows[offset:offset + limit + 1]
    return {'items': [phone_dict(a, r) for a, r in page[:limit]],
            'next_offset': offset + limit if len(page) > limit else None}


# ---------- contacts by first capture ----------

async def contact_rows(session, date_from=None, date_to=None, account_id=None):
    """(PhoneRegistry, Live|None): one row per contact, selected by its FIRST capture."""
    query = (select(PhoneRegistry, Live)
             .outerjoin(Live, Live.id == PhoneRegistry.first_live_id)
             .order_by(PhoneRegistry.first_captured_at.desc(), PhoneRegistry.id.desc())
             .limit(ROW_CAP * 10))
    if date_from is not None:
        query = query.where(PhoneRegistry.first_captured_at >= date_from)
    if date_to is not None:
        query = query.where(PhoneRegistry.first_captured_at < date_to)
    if account_id:
        query = query.where(PhoneRegistry.first_account_id == account_id)
    return (await session.execute(query)).all()


def as_window(contact: PhoneRegistry):
    """A zero-length 'live' so shift attribution can load shifts around a capture."""
    return SimpleNamespace(account_id=contact.first_account_id,
                           started_at=contact.first_captured_at,
                           ended_at=contact.first_captured_at)


def owner_of(attribution, contact: PhoneRegistry, live: Live | None):
    if not contact.first_account_id:
        return None, UNASSIGNED
    fallback = live.tiktoker_id if live is not None else None
    return attribution.at(contact.first_account_id, contact.first_captured_at, fallback)


async def scoped_contacts(session, date_from, date_to, tiktoker_id, account_id):
    rows = await contact_rows(session, date_from, date_to, account_id)
    attribution = await load_attribution(session, [as_window(c) for c, _ in rows])
    if tiktoker_id:
        rows = [(c, live) for c, live in rows if owner_of(attribution, c, live)[0] == tiktoker_id]
    return rows, attribution


def new_stats():
    return {'phones': 0, 'contacted': 0, 'qualified': 0, 'seconds': []}


def add_contact(stats, contact: PhoneRegistry):
    stats['phones'] += 1
    stats['contacted'] += contact.contacted_at is not None
    stats['qualified'] += contact.status == 'qualified'
    if contact.contacted_at is not None:
        stats['seconds'].append(contact_time_seconds(contact))


# ---------- dashboards ----------

async def overview(session, tiktoker_id=None, **filters):
    date_from, date_to = filters.get('date_from'), filters.get('date_to')
    account_id = filters.get('account_id')
    rows = await fetch_lives(session, **filters)
    live_list = [r[0] for r in rows]
    attribution = await load_attribution(session, live_list)
    total = {f: 0.0 for f in METRIC_FIELDS}
    seconds, count, live_now, peak = 0.0, 0, 0, 0
    for live, metrics, _ in rows:
        shares = attribution.shares(live)
        if not involves(shares, tiktoker_id):
            continue
        fraction = shares[tiktoker_id][1] if tiktoker_id else 1.0
        count += 1
        live_now += live.status == 'live'
        seconds += seconds_of(live) * fraction
        if metrics:
            peak = max(peak, metrics.peak_viewers)
            for f in METRIC_FIELDS:
                value = getattr(metrics, f)
                total[f] += value * (fraction if f in ALLOCATED else 1)
    contacts, _ = await scoped_contacts(session, date_from, date_to, tiktoker_id, account_id)
    phones = len(contacts)
    contacted = sum(c.contacted_at is not None for c, _ in contacts)
    for f in ALLOCATED:
        total[f] = round(total[f])
    return {'lives': count, 'live_now': live_now,
            'views': total['views'],
            'peak_viewers': peak,                 # highest simultaneous audience in any live
            'unique_viewers': None,               # no source connected: not available
            'comments': total['comments_count'], 'likes': total['likes_count'],
            'shares': total['shares_count'], 'followers': total['new_followers'],
            'interested': total['interested_viewers'], 'donations': total['donations_count'],
            'direct_messages_reported': int(total['direct_messages_count']),
            'direct_messages_capture': settings.dm_capture_connected,
            'phones': phones, 'phones_contacted': contacted,
            'phone_mentions': int(total['phone_mentions']),
            'live_hours': round(seconds / 3600, 2), 'leads_per_hour': rate(phones, seconds),
            'note': 'phones cuenta contactos únicos por la fecha de su PRIMERA captura. '
                    'Los contadores del live se reparten por tiempo de turno cuando se filtra '
                    'por tiktoker_id. unique_viewers no está disponible.'}


SORTS = {'phones': 'phones', 'leads_per_hour': 'leads_per_hour', 'views': 'views',
         'interested': 'interested', 'conversion': 'conversion'}


async def ranking(session, sort_by, **filters):
    rows = await fetch_lives(session, **filters)
    attribution = await load_attribution(session, [r[0] for r in rows])
    board: dict = {}

    def entry(key, name):
        return board.setdefault(key, {
            'tiktoker_id': key, 'tiktoker': name, 'lives': 0, 'views': 0.0, 'interested': 0.0,
            'comments': 0.0, 'seconds': 0.0, 'stats': new_stats()})

    for live, metrics, _ in rows:
        for key, (name, fraction) in attribution.shares(live).items():
            r = entry(key, name)
            r['lives'] += 1
            r['seconds'] += seconds_of(live) * fraction
            if metrics:
                r['views'] += metrics.views * fraction
                r['interested'] += metrics.interested_viewers * fraction
                r['comments'] += metrics.comments_count * fraction
    contacts, contact_attr = await scoped_contacts(
        session, filters.get('date_from'), filters.get('date_to'), None, filters.get('account_id'))
    for contact, live in contacts:
        key, name = owner_of(contact_attr, contact, live)
        add_contact(entry(key, name)['stats'], contact)
    items = []
    for key, r in board.items():
        s = r['stats']
        items.append({
            'tiktoker_id': key, 'tiktoker': r['tiktoker'], 'lives': r['lives'],
            'live_hours': round(r['seconds'] / 3600, 2), 'views': round(r['views']),
            'interested': round(r['interested']), 'comments': round(r['comments']),
            'phones': s['phones'], 'contacted': s['contacted'], 'qualified': s['qualified'],
            'leads_per_hour': rate(s['phones'], r['seconds']),
            # conversion = contacts that reached "qualified" / contacts captured.
            'conversion': round(s['qualified'] / s['phones'], 4) if s['phones'] else 0.0})
    assigned = sorted((i for i in items if i['tiktoker_id'] is not None),
                      key=lambda i: (i[SORTS[sort_by]], i['phones']), reverse=True)
    for position, item in enumerate(assigned, 1):
        item['rank'] = position
    unassigned = [{**i, 'rank': None} for i in items if i['tiktoker_id'] is None]
    return {'sort_by': sort_by, 'items': assigned + unassigned}


async def accounts_performance(session, tiktoker_id=None, **filters):
    rows = await fetch_lives(session, **filters)
    attribution = await load_attribution(session, [r[0] for r in rows])
    board: dict = {}
    accounts = {a.id: a for a in (await session.scalars(select(TiktokAccount))).all()}

    def entry(account):
        return board.setdefault(account.id, {
            'account_id': account.id, 'account': '@' + account.username, 'name': account.name,
            'type': account.type, 'lives': 0, 'views': 0.0, 'comments': 0.0, 'likes': 0.0,
            'interested': 0.0, 'donations': 0.0, 'seconds': 0.0, 'stats': new_stats(),
            'unassigned_phones': 0})

    for live, metrics, account in rows:
        shares = attribution.shares(live)
        if not involves(shares, tiktoker_id):
            continue
        fraction = shares[tiktoker_id][1] if tiktoker_id else 1.0
        r = entry(account)
        r['lives'] += 1
        r['seconds'] += seconds_of(live) * fraction
        if metrics:
            r['views'] += metrics.views * fraction
            r['comments'] += metrics.comments_count * fraction
            r['likes'] += metrics.likes_count * fraction
            r['interested'] += metrics.interested_viewers * fraction
            r['donations'] += metrics.donations_count * fraction
    contacts, contact_attr = await scoped_contacts(
        session, filters.get('date_from'), filters.get('date_to'), tiktoker_id,
        filters.get('account_id'))
    for contact, live in contacts:
        account = accounts.get(contact.first_account_id)
        if account is None:
            continue
        r = entry(account)
        add_contact(r['stats'], contact)
        r['unassigned_phones'] += owner_of(contact_attr, contact, live)[0] is None
    items = []
    for r in board.values():
        s, seconds = r.pop('stats'), r.pop('seconds')
        for f in ('views', 'comments', 'likes', 'interested', 'donations'):
            r[f] = round(r[f])
        items.append({**r, 'live_hours': round(seconds / 3600, 2), 'phones': s['phones'],
                      'contacted': s['contacted'], 'qualified': s['qualified'],
                      'leads_per_hour': rate(s['phones'], seconds)})
    items.sort(key=lambda i: i['phones'], reverse=True)
    return {'items': items}


def bucket_key(moment, granularity):
    local = aware_utc(moment).astimezone(LIMA)
    if granularity == 'hour_of_day':
        return local.hour
    if granularity == 'day':
        return local.date().isoformat()
    if granularity == 'week':
        return (local.date() - timedelta(days=local.weekday())).isoformat()
    return local.strftime('%Y-%m')


async def hourly(session, granularity, date_from, date_to, tiktoker_id, account_id):
    rows, _ = await scoped_contacts(session, date_from, date_to, tiktoker_id, account_id)
    counts: dict = {}
    for contact, _ in rows:
        key = bucket_key(contact.first_captured_at, granularity)
        counts[key] = counts.get(key, 0) + 1
    result: dict = {'granularity': granularity, 'timezone': 'America/Lima', 'total': len(rows),
                    'basis': 'first_capture'}
    if granularity != 'hour_of_day':
        result['items'] = [{'period': k, 'phones': v} for k, v in sorted(counts.items())]
        return result
    # Hours when at least one live was on air: a quiet 3 AM is not the "worst" hour.
    lives = await fetch_lives(session, date_from, date_to, account_id)
    active: set[int] = set()
    for live, _, _ in lives:
        cursor = aware_utc(live.started_at).astimezone(LIMA).replace(
            minute=0, second=0, microsecond=0)
        end = live_end(live).astimezone(LIMA)
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
    rows, _ = await scoped_contacts(session, date_from, date_to, tiktoker_id, account_id)
    seconds = sorted(contact_time_seconds(c) for c, _ in rows if c.contacted_at is not None)
    pending = sum(1 for c, _ in rows if c.contacted_at is None and c.status == 'new')
    pct = {}
    for name, low, high in BUCKETS:
        n = sum(1 for s in seconds if s >= low and (high is None or s < high))
        pct[name] = round(100 * n / len(seconds), 1) if seconds else 0.0
    return {'phones': len(rows), 'contacted': len(seconds), 'uncontacted': pending,
            'average_seconds': round(sum(seconds) / len(seconds), 1) if seconds else None,
            'median_seconds': round(median(seconds), 1) if seconds else None,
            'min_seconds': seconds[0] if seconds else None,
            'max_seconds': seconds[-1] if seconds else None,
            'percent': pct, 'percent_base': 'phones contacted', 'basis': 'first_capture'}


# ---------- views for Medical 360 ----------

async def monitor(session):
    """One row per account: who is on air, since when, and the live's figures."""
    states = {s.account_id: s for s in (await session.scalars(select(MonitorState))).all()}
    names = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    for account_id, username in settings.tiktok_accounts.items():
        names.setdefault(account_id, username)
    out = []
    for account_id, username in names.items():
        live = await session.scalar(select(Live).where(Live.account_id == account_id)
                                    .order_by((Live.status == 'live').desc(),
                                              Live.started_at.desc()).limit(1))
        metrics = await session.scalar(select(LiveMetrics).where(
            LiveMetrics.live_id == live.id)) if live else None
        on_air = bool(live and live.status == 'live')
        shift = await session.scalar(select(Shift).where(
            Shift.account_id == account_id, Shift.ended_at.is_(None)))
        who = None
        if shift:
            who = shift.display_name or shift.user_id
        pending_contacts = 0
        if live:
            pending_contacts = await session.scalar(
                select(func.count()).select_from(PhoneRegistry).where(
                    PhoneRegistry.first_live_id == live.id, PhoneRegistry.status == 'new')) or 0
        state = states.get(account_id)
        out.append({
            'account_id': account_id, 'account': '@' + username,
            'status': state.status if state else 'not_started',
            'heartbeat': iso(state.observed_at) if state else None,
            'on_air': on_air, 'live_id': live.id if live else None,
            'tiktoker': who,   # who has the shift now; None = nobody checked in
            'started_at': stamp(live.started_at if live else None),
            'ended_at': stamp(live.ended_at if live else None),
            'metrics': metrics_dict(metrics) if live else None,
            'contacts': metrics.phones_captured if metrics else 0,
            'contacts_pending': pending_contacts})
    return {'generated_at': stamp(utcnow()), 'accounts': out}


async def inbox(session, since=None, limit=100, only_with_phone=False, account_id=None):
    """Latest live comments with their contact's attention state. Comment text exists only
    inside the retention window."""
    since = since or utcnow() - timedelta(hours=24)
    query = (select(LiveComment, Live).join(Live, Live.id == LiveComment.live_id)
             .where(LiveComment.created_at >= since)
             .order_by(LiveComment.created_at.desc(), LiveComment.id.desc()).limit(limit))
    if only_with_phone:
        query = query.where(LiveComment.phone_detected.is_not(None))
    if account_id:
        query = query.where(Live.account_id == account_id)
    rows = (await session.execute(query)).all()
    attribution = await load_attribution(session, [live for _, live in rows])
    phones = {c.phone_detected for c, _ in rows if c.phone_detected}
    contacts = {}
    if phones:
        contacts = {r.phone: r for r in (await session.scalars(select(PhoneRegistry).where(
            PhoneRegistry.phone.in_(phones)))).all()}
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    items = []
    for comment, live in rows:
        contact = contacts.get(comment.phone_detected)
        who_id, who = attribution.at(live.account_id, comment.created_at, live.tiktoker_id)
        kind = ('Cliente potencial' if comment.phone_detected
                else 'Interesado' if comment.interested else 'Comentario')
        items.append({
            'comment_id': comment.id, 'live_id': live.id, 'account_id': live.account_id,
            'account': '@' + accounts.get(live.account_id, live.account_id), 'origin': 'live',
            'tiktok_username': '@' + comment.username.lstrip('@'),
            'tiktoker_id': who_id, 'tiktoker': who,
            'comment': comment.comment,
            'phones': [comment.phone_detected] if comment.phone_detected else [],
            'is_first_capture': bool(contact and contact.first_live_id == live.id
                                     and aware_utc(contact.first_captured_at)
                                     == aware_utc(comment.created_at)),
            'kind': kind,
            'state': STATE_LABEL.get(contact.status) if contact else None,
            'received_at': stamp(comment.created_at),
            'contacted_at': stamp(contact.contacted_at) if contact else stamp(None)})
    return {'generated_at': stamp(utcnow()), 'since': stamp(since), 'items': items,
            'direct_messages': None, 'direct_messages_capture': settings.dm_capture_connected}


async def numbers(session, date_from, date_to, tiktoker_id=None, account_id=None):
    """Received numbers for Medical 360: unique contacts by FIRST capture, plus the list so a
    consumer can match them without re-deriving the rule."""
    rows, attribution = await scoped_contacts(session, date_from, date_to, tiktoker_id,
                                              account_id)
    by_account: dict = {}
    by_tiktoker: dict = {}
    by_hour: dict = {}
    contacted = from_live = from_dm = 0
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    phones = []
    for contact, live in rows:
        who_id, who = owner_of(attribution, contact, live)
        by_account[contact.first_account_id] = by_account.get(contact.first_account_id, 0) + 1
        by_tiktoker[who] = by_tiktoker.get(who, 0) + 1
        hour = aware_utc(contact.first_captured_at).astimezone(LIMA).hour
        by_hour[hour] = by_hour.get(hour, 0) + 1
        contacted += contact.contacted_at is not None
        from_live += contact.first_source != 'direct_message'
        from_dm += contact.first_source == 'direct_message'
        phones.append({
            'phone': contact.phone, 'account_id': contact.first_account_id,
            'account': '@' + accounts.get(contact.first_account_id, contact.first_account_id or ''),
            'live_id': contact.first_live_id, 'tiktoker_id': who_id, 'tiktoker': who,
            'source': contact.first_source, 'state': STATE_LABEL.get(contact.status),
            'first_captured_at': stamp(contact.first_captured_at),
            'contacted_at': stamp(contact.contacted_at)})
    return {
        'basis': 'first_capture', 'timezone': 'America/Lima',
        'received': len(rows), 'from_live': from_live,
        'from_dm': from_dm if settings.dm_capture_connected else None,
        'contacted': contacted, 'by_account': by_account, 'by_tiktoker': by_tiktoker,
        'by_hour': [{'hour': h, 'count': c} for h, c in sorted(by_hour.items())],
        'phones': phones[:5000], 'truncated': len(phones) > 5000}
