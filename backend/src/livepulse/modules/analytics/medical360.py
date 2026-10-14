"""Read models for Medical 360 (server-to-server): per-account monitor and comment inbox."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select

from ...shared.config import settings
from ..broadcasts.models import RawEvent
from ..shifts.models import Shift
from .models import EventFact as F
from .models import Lead, LeadAudit
from .reporting import lives, shift_join

LIMA = ZoneInfo('America/Lima')
# LivePulse lead status -> label shown in Medical 360.
STATE = {'new': 'Por contactar', 'ready': 'Por contactar', 'contacted': 'Contactado',
         'scheduled': 'Cita agendada', 'closed': 'Cerrado', 'invalid': 'Descartado'}
PENDING = ('new', 'ready')


def stamp(value):
    """UTC instant plus the same instant in Lima, so the consumer never guesses a zone."""
    if value is None:
        return {'utc': None, 'lima': None}
    return {'utc': value.astimezone(timezone.utc).isoformat(),
            'lima': value.astimezone(LIMA).isoformat()}


def kind_of(phones, interested):
    if phones:
        return 'Cliente potencial'
    return 'Interesado' if interested else 'Comentario'


async def monitor(session):
    rows = []
    for account, username in settings.tiktok_accounts.items():
        latest = (await lives(session, account, 1))['items']
        live = latest[0] if latest else None
        shift = await session.scalar(select(Shift).where(
            Shift.account_id == account, Shift.ended_at.is_(None)))
        pending_contacts = 0
        if live:
            pending_contacts = await session.scalar(
                select(func.count(distinct(F.lead_id))).join(Lead, Lead.id == F.lead_id)
                .where(F.broadcast_id == live['id'], Lead.status.in_(PENDING)))
        metrics = live['metrics'] if live else {}
        rows.append({
            'account_id': account, 'account': '@' + username,
            'on_air': bool(live and live['ended_at'] is None),
            'broadcast_id': live['id'] if live else None,
            'tiktoker_id': shift.user_id if shift else None,
            'tiktoker': (shift.display_name or shift.user_id) if shift else None,
            'started_at': stamp(live['started_at'] if live else None),
            'ended_at': stamp(live['ended_at'] if live else None),
            'end_confirmed': live['end_confirmed'] if live else None,
            'peak_viewers': metrics.get('peak_viewers'),
            'average_viewers': metrics.get('average_sampled_viewers'),
            'comments': metrics.get('comments', 0), 'likes': metrics.get('likes', 0),
            'shares': metrics.get('shares', 0),
            'observed_followers': metrics.get('observed_followers', 0),
            'donors': metrics.get('donors', 0), 'interested': metrics.get('interested_users', 0),
            'contacts': metrics.get('leads', 0), 'contacts_pending': pending_contacts or 0,
            'pending_events': live['pending_events'] if live else 0})
    return {'generated_at': stamp(datetime.now(timezone.utc)), 'accounts': rows}


async def inbox(session, since=None, limit=100, only_with_phone=False, account_id=None):
    now = datetime.now(timezone.utc)
    since = since or now - timedelta(hours=24)
    query = (select(F.event_id, F.account_id, F.user_key, F.occurred_at, F.phones, F.interested,
                    F.lead_id, F.broadcast_id, RawEvent.raw_text, RawEvent.payload, Lead.status,
                    Shift.user_id, Shift.display_name)
             .join(RawEvent, RawEvent.event_id == F.event_id)
             .outerjoin(Lead, Lead.id == F.lead_id)
             .outerjoin(Shift, shift_join())
             .where(F.kind == 'comment', F.occurred_at >= since)
             .order_by(F.occurred_at.desc(), F.event_id).limit(limit))
    if account_id:
        query = query.where(F.account_id == account_id)
    if only_with_phone:
        query = query.where(F.lead_id.is_not(None))
    rows = (await session.execute(query)).all()
    if only_with_phone:
        rows = [r for r in rows if r.phones]
    contacted = {}
    lead_ids = {r.lead_id for r in rows if r.lead_id}
    if lead_ids:
        for lead_id, at in (await session.execute(
                select(LeadAudit.lead_id, func.min(LeadAudit.created_at))
                .where(LeadAudit.lead_id.in_(lead_ids), LeadAudit.action == 'status',
                       LeadAudit.value == 'contacted').group_by(LeadAudit.lead_id))).all():
            contacted[lead_id] = at
    accounts = settings.tiktok_accounts
    items = []
    for r in rows:
        handle = (r.payload or {}).get('username')
        items.append({
            'event_id': r.event_id, 'account_id': r.account_id,
            'account': '@' + accounts.get(r.account_id, r.account_id),
            'origin': 'live', 'broadcast_id': r.broadcast_id,
            'tiktok_user_id': r.user_key, 'tiktok_username': ('@' + handle) if handle else None,
            'tiktok_nickname': (r.payload or {}).get('nickname'),
            'tiktoker_id': r.user_id, 'tiktoker': r.display_name or r.user_id,
            'comment': r.raw_text or '', 'phones': list(r.phones or []),
            'kind': kind_of(r.phones, r.interested),
            'state': STATE.get(r.status, 'Por contactar') if r.lead_id else None,
            'received_at': stamp(r.occurred_at),
            'contacted_at': stamp(contacted.get(r.lead_id)) if r.lead_id else stamp(None),
            'lead_id': r.lead_id})
    return {'generated_at': stamp(now), 'since': stamp(since), 'items': items,
            'direct_messages': None}
