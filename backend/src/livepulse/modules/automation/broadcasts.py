"""Mass messages ("difusiones").

Built to be shown, not to be used often: on the WhatsApp mirror they are OFF by default and, even
when an admin turns them on, only reach the channel's test numbers inside a daily cap (see
chat/policy.py). On the official channel they are the normal tool. The same rules apply to every
recipient: opt-outs are skipped, a daily cap and a pause between messages are respected, and a
policy block pauses the whole broadcast instead of retrying forever.

Life of a broadcast: draft (audience preview, test message) -> start (the admin confirms the exact
number of recipients) -> sending in small batches by the worker -> done. It can be paused,
resumed or cancelled at any time."""
import re
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update

from ..chat.models import ChatChannel, OptOut
from ..chat.policy import PolicyViolation
from ..chat.service import aware, get_conversation, send_message, utcnow
from .models import Broadcast, BroadcastRecipient

BATCH = 5
MAX_AUDIENCE = 5000
HARD_STOP = {'broadcasts_disabled', 'test_only', 'daily_cap', 'channel_disabled',
             'channel_unavailable'}
FILTERS = {'statuses', 'live_ids', 'sources', 'captured_from', 'captured_to',
           'exclude_contacted_days', 'phones'}


def render(body: str, name: str | None) -> str:
    def fill(match):
        return (name if match.group(1) == 'nombre' and name else (match.group(2) or '')).strip()

    return re.sub(r'\{\{\s*(\w+)\s*(?:\|([^}]*))?\}\}', fill, body).strip()


def clean_audience(raw: dict) -> dict:
    unknown = set(raw) - FILTERS
    if unknown:
        raise ValueError(f'Filtro desconocido: {", ".join(sorted(unknown))}')
    audience = dict(raw)
    audience['statuses'] = [s for s in audience.get('statuses', ['new'])
                            if s in ('new', 'contacted', 'qualified')] or ['new']
    audience['exclude_contacted_days'] = max(0, min(int(audience.get('exclude_contacted_days', 0)), 365))
    return audience


async def _audience_query(session, audience: dict, now: datetime):
    from ..social_live.models import PhoneRegistry
    query = select(PhoneRegistry.phone, PhoneRegistry.first_username).where(
        PhoneRegistry.status.in_(audience['statuses']),
        ~PhoneRegistry.phone.in_(select(OptOut.phone)))
    if audience.get('live_ids'):
        query = query.where(PhoneRegistry.first_live_id.in_(audience['live_ids']))
    if audience.get('sources'):
        query = query.where(PhoneRegistry.first_source.in_(audience['sources']))
    if audience.get('captured_from'):
        query = query.where(PhoneRegistry.first_captured_at >= audience['captured_from'])
    if audience.get('captured_to'):
        query = query.where(PhoneRegistry.first_captured_at <= audience['captured_to'])
    if audience.get('phones'):
        query = query.where(PhoneRegistry.phone.in_(audience['phones']))
    days = audience.get('exclude_contacted_days', 0)
    if days:
        query = query.where(or_(PhoneRegistry.contacted_at.is_(None),
                                PhoneRegistry.contacted_at < now - timedelta(days=days)))
    return query.order_by(PhoneRegistry.first_captured_at, PhoneRegistry.id)


async def preview(session, audience: dict, now: datetime | None = None) -> dict:
    audience = clean_audience(audience)
    query = await _audience_query(session, audience, now or utcnow())
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    sample = (await session.execute(query.limit(5))).all()
    return {'count': total, 'sample': [{'phone': p, 'name': n} for p, n in sample],
            'capped': total > MAX_AUDIENCE}


async def create(session, actor: str, name: str, channel_id: str, body: str,
                 audience: dict) -> Broadcast:
    channel = await session.get(ChatChannel, channel_id)
    if channel is None:
        raise ValueError('Canal inexistente.')
    audience = clean_audience(audience)
    if not body.strip() or len(body) > 1000:
        raise ValueError('El mensaje debe tener entre 1 y 1000 caracteres.')
    now = utcnow()
    broadcast = Broadcast(name=name.strip()[:120], channel_id=channel_id, body=body.strip(),
                          audience=audience, status='draft', created_by=actor, created_at=now)
    session.add(broadcast)
    await session.flush()
    rows = (await session.execute((await _audience_query(session, audience, now))
                                  .limit(MAX_AUDIENCE))).all()
    session.add_all([BroadcastRecipient(broadcast_id=broadcast.id, phone=p, name=n)
                     for p, n in rows])
    broadcast.total = len(rows)
    await session.flush()
    return broadcast


async def test_send(session, broadcast: Broadcast, phone: str, now: datetime | None = None):
    """The message exactly as a recipient would get it, to ONE number (it counts against the
    same policy, so on the mirror the number must be in the test list)."""
    from ..chat.service import normalize
    phone = normalize(phone)
    conversation = await get_conversation(session, broadcast.channel_id, phone)
    return await send_message(session, conversation, render(broadcast.body, conversation.contact_name),
                              author_kind='bot', author_id='broadcast:test',
                              broadcast_id=broadcast.id, now=now)


async def start(session, broadcast: Broadcast, confirm_total: int, scheduled_at=None,
                now: datetime | None = None) -> Broadcast:
    now = now or utcnow()
    if broadcast.status not in ('draft', 'paused'):
        raise ValueError('Solo se puede iniciar una difusión en borrador o en pausa.')
    pending = await session.scalar(select(func.count()).select_from(BroadcastRecipient).where(
        BroadcastRecipient.broadcast_id == broadcast.id,
        BroadcastRecipient.status == 'pending')) or 0
    if confirm_total != pending or pending == 0:
        raise ValueError(f'Confirma el número exacto de destinatarios: son {pending}.')
    broadcast.pause_reason = None
    if scheduled_at and aware(scheduled_at) > now:
        broadcast.status, broadcast.scheduled_at = 'scheduled', aware(scheduled_at)
    else:
        broadcast.status, broadcast.started_at = 'sending', broadcast.started_at or now
    return broadcast


async def set_state(session, broadcast: Broadcast, action: str, now: datetime | None = None):
    now = now or utcnow()
    if action == 'pause' and broadcast.status in ('scheduled', 'sending'):
        broadcast.status, broadcast.pause_reason = 'paused', 'Pausada por un administrador.'
    elif action == 'resume' and broadcast.status == 'paused':
        broadcast.status, broadcast.pause_reason = 'sending', None
    elif action == 'cancel' and broadcast.status in ('draft', 'scheduled', 'sending', 'paused'):
        broadcast.status, broadcast.finished_at = 'cancelled', now
    else:
        raise ValueError('Esa acción no corresponde al estado actual.')
    return broadcast


async def _pause(broadcast: Broadcast, reason: str):
    broadcast.status, broadcast.pause_reason = 'paused', reason[:200]


async def tick(factory, now: datetime | None = None) -> int:
    """Send the next small batch of every broadcast that is sending (or due)."""
    now = now or utcnow()
    sent_now = 0
    async with factory() as session, session.begin():
        await session.execute(update(Broadcast).where(
            Broadcast.status == 'scheduled', Broadcast.scheduled_at <= now)
            .values(status='sending', started_at=now))
        active = (await session.scalars(select(Broadcast).where(Broadcast.status == 'sending')
                                        .order_by(Broadcast.id))).all()
        for broadcast in active:
            batch = (await session.scalars(select(BroadcastRecipient).where(
                BroadcastRecipient.broadcast_id == broadcast.id,
                BroadcastRecipient.status == 'pending').order_by(BroadcastRecipient.id)
                .limit(BATCH))).all()
            if not batch:
                broadcast.status, broadcast.finished_at = 'done', now
                continue
            for recipient in batch:
                conversation = await get_conversation(session, broadcast.channel_id,
                                                      recipient.phone, recipient.name)
                try:
                    await send_message(session, conversation,
                                       render(broadcast.body, conversation.contact_name),
                                       author_kind='bot', author_id=f'broadcast:{broadcast.id}',
                                       broadcast_id=broadcast.id, now=now)
                except PolicyViolation as problem:
                    if problem.code == 'opted_out':
                        recipient.status, recipient.error = 'skipped', problem.code
                        broadcast.skipped += 1
                        continue
                    if problem.code in HARD_STOP:
                        await _pause(broadcast, problem.message)
                    break  # rate limits (retry) just wait for the next tick
                recipient.status, recipient.sent_at = 'sent', now
                broadcast.sent += 1
                sent_now += 1
    return sent_now
