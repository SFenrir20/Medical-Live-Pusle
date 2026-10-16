"""Ingestion rules. Counters are consolidated in live_metrics as events arrive, so dashboards
never count raw comments. Portable SQL: increments are atomic UPDATEs, duplicates are detected
with a savepoint instead of dialect-specific upserts.

Contacts: a phone number is ONE contact (phone_registry), created at its first capture on any
account. Later appearances are stored in captured_phones and never counted as new."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import phonenumbers
from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from ...shared.config import settings
from ..analytics.classify import interested_in, phones_in
from . import titles
from .models import (
    CapturedPhone,
    ContactAudit,
    Live,
    LiveComment,
    LiveEventKey,
    LiveInterestedUser,
    LiveMetrics,
    PhoneRegistry,
    TiktokAccount,
    Tiktoker,
)
from .schemas import EventIn

LATE_EVENT_GRACE = timedelta(minutes=5)
SOURCE_BY_EVENT = {'phone_detected': 'comment', 'phone_manual': 'manual_capture'}
COUNTER = {'like': 'likes_count', 'view': 'views', 'share': 'shares_count',
           'follow': 'new_followers', 'donation': 'donations_count'}


def utcnow():
    return datetime.now(timezone.utc)


def aware_utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def normalize_phone(raw: str, region='PE') -> str | None:
    """E.164, or None. The same number written any way is the same contact."""
    found = phones_in(raw, region)
    if found:
        return found[0]
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


async def require_live(session, live_id: str) -> Live:
    live = await session.get(Live, live_id)
    if live is None:
        raise HTTPException(404, 'Live no encontrado.')
    return live


async def code_map(session) -> dict[str, str]:
    """{code: tiktoker id} of the active TikTokers that have a code."""
    rows = (await session.execute(select(Tiktoker.code, Tiktoker.id).where(
        Tiktoker.code.is_not(None), Tiktoker.active.is_(True)))).all()
    return {code.upper(): tid for code, tid in rows}


async def apply_title(session, live: Live, title) -> bool:
    """Record the title and, when it names exactly one TikToker, make her the responsible.

    A responsible set by hand is never overridden. A title without a (single) code never
    clears one that an earlier title identified. Returns True if the responsible changed."""
    title = titles.clean_title(title)
    if title is None:
        return False
    live.title = title
    if live.responsible_source == 'manual':
        return False
    found, _ = titles.resolve(title, await code_map(session))
    if found is None or found == live.tiktoker_id:
        return False
    live.tiktoker_id, live.responsible_source = found, 'title'
    live.updated_at = utcnow()
    return True


async def create_live(session, body) -> tuple[Live, bool]:
    now = utcnow()
    if body.live_id:
        existing = await session.get(Live, body.live_id)
        if existing is not None:
            if existing.account_id != body.account_id or (
                    body.tiktoker_id and existing.tiktoker_id not in (None, body.tiktoker_id)):
                raise HTTPException(409, 'Ese live_id ya existe con otra cuenta o TikToker.')
            return existing, False
    tiktoker = await session.get(Tiktoker, body.tiktoker_id) if body.tiktoker_id else None
    account = await session.get(TiktokAccount, body.account_id)
    if body.tiktoker_id and (tiktoker is None or not tiktoker.active):
        raise HTTPException(422, 'TikToker inexistente o inactivo.')
    if account is None or not account.active:
        raise HTTPException(422, 'Cuenta TikTok inexistente o inactiva.')
    live = Live(id=body.live_id or 'LIVE-' + uuid4().hex[:10].upper(),
                tiktoker_id=body.tiktoker_id, account_id=body.account_id,
                responsible_source='manual' if body.tiktoker_id else None,
                started_at=body.started_at or now, status=body.status,
                created_at=now, updated_at=now)
    session.add(live)
    session.add(LiveMetrics(live_id=live.id, created_at=now, updated_at=now))
    await session.flush()
    await apply_title(session, live, body.title)
    return live, True


async def update_live(session, live: Live, body) -> Live:
    """Correct a live's title and/or responsible. A given tiktoker_id is a manual assignment;
    an explicit null hands the decision back to the title."""
    fields = body.model_fields_set
    if 'tiktoker_id' in fields:
        if body.tiktoker_id is None:
            live.tiktoker_id, live.responsible_source = None, None
        else:
            tiktoker = await session.get(Tiktoker, body.tiktoker_id)
            if tiktoker is None or not tiktoker.active:
                raise HTTPException(422, 'TikToker inexistente o inactivo.')
            live.tiktoker_id, live.responsible_source = body.tiktoker_id, 'manual'
    if 'title' in fields:
        live.title = titles.clean_title(body.title)
    if live.responsible_source != 'manual' and live.title:
        await apply_title(session, live, live.title)
    live.updated_at = utcnow()
    return live


async def _claim_event(session, live_id, event_id) -> bool:
    """False if this client retry was already applied."""
    if not event_id:
        return True
    try:
        async with session.begin_nested():
            session.add(LiveEventKey(live_id=live_id, event_id=event_id))
            await session.flush()
    except IntegrityError:
        return False
    return True


async def claim_interest(session, live_id, username) -> bool:
    # The composite primary key serializes concurrent comments from the same viewer.
    try:
        async with session.begin_nested():
            session.add(LiveInterestedUser(live_id=live_id, username=username))
            await session.flush()
    except IntegrityError:
        return False
    return True


async def _bump(session, live_id, column, amount):
    if amount <= 0:
        return
    await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live_id).values(
        **{column: getattr(LiveMetrics, column) + amount, 'updated_at': utcnow()}))


async def audit(session, registry_id, actor, action, previous=None, value=None):
    session.add(ContactAudit(registry_id=registry_id, actor=actor, action=action,
                             previous=previous, value=value))


# ---------- contacts (global registry) ----------

async def save_phone(session, live: Live, phone, username, source, captured_at):
    """Record one appearance of `phone` in `live`.

    Returns ('new' | 'mention' | None, affected live ids).
      new      first time this number is ever seen (it becomes the contact's first capture)
      mention  a known contact appeared in this live for the first time
      None     already recorded in this live

    Concurrency: the unique phone makes the first insert win; the loser becomes a mention.
    If the loser's capture time is EARLIER (events can arrive out of order), it becomes the
    first capture and the previous one is demoted, so reports attribute by true first time."""
    captured_at = aware_utc(captured_at)
    affected = {live.id}
    is_new = True
    try:
        async with session.begin_nested():
            session.add(PhoneRegistry(
                phone=phone, first_live_id=live.id, first_account_id=live.account_id,
                first_captured_at=captured_at, first_username=username, first_source=source,
                status='new'))
            await session.flush()
    except IntegrityError:
        is_new = False
    registry = await session.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == phone))
    if is_new:
        await audit(session, registry.id, 'system', 'captured', None, live.id)
    elif captured_at < aware_utc(registry.first_captured_at):
        previous = await session.scalar(select(CapturedPhone).where(
            CapturedPhone.phone == phone, CapturedPhone.is_new.is_(True)))
        if previous is not None:
            previous.is_new = False
            affected.add(previous.live_id)
        registry.first_live_id, registry.first_account_id = live.id, live.account_id
        registry.first_captured_at, registry.first_username = captured_at, username
        registry.first_source, registry.updated_at = source, utcnow()
        is_new = True
    elif registry.first_live_id == live.id and not await session.scalar(
            select(CapturedPhone.id).where(CapturedPhone.phone == phone,
                                           CapturedPhone.is_new.is_(True))):
        # Contact converted from older data: this appearance IS its first capture.
        is_new = True

    existing = await session.scalar(select(CapturedPhone).where(
        CapturedPhone.live_id == live.id, CapturedPhone.phone == phone))
    if existing is not None:
        if is_new:  # an earlier capture inside the same live
            existing.captured_at, existing.is_new = captured_at, True
            existing.tiktok_username, existing.source = username, source
        elif aware_utc(existing.captured_at) > captured_at:
            existing.captured_at = captured_at
        return None, affected
    try:
        async with session.begin_nested():
            session.add(CapturedPhone(live_id=live.id, phone=phone, tiktok_username=username,
                                      source=source, captured_at=captured_at, is_new=is_new))
            await session.flush()
    except IntegrityError:
        return None, affected  # a concurrent writer recorded this appearance
    return ('new' if is_new else 'mention'), affected


async def refresh_derived(session, live: Live):
    """Phone counters come from the stored rows, not from increments.
    phones_captured = numbers whose FIRST capture was in this live; phone_mentions = every
    appearance in it."""
    phones = await session.scalar(select(func.count()).select_from(CapturedPhone).where(
        CapturedPhone.live_id == live.id, CapturedPhone.is_new.is_(True))) or 0
    mentions = await session.scalar(select(func.count()).select_from(CapturedPhone)
                                    .where(CapturedPhone.live_id == live.id)) or 0
    end = live.ended_at or utcnow()
    seconds = max(60.0, (aware_utc(end) - aware_utc(live.started_at)).total_seconds())
    await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live.id).values(
        phones_captured=phones, phone_mentions=mentions,
        leads_per_hour=round(phones / (seconds / 3600), 2), updated_at=utcnow()))


async def refresh_many(session, live: Live, live_ids):
    for live_id in live_ids:
        target = live if live_id == live.id else await session.get(Live, live_id)
        if target is not None:
            await refresh_derived(session, target)


def too_old_error():
    return HTTPException(409, {
        'code': 'EVENT_TOO_OLD',
        'message': f'El evento es anterior a {settings.comments_retention_days} días: ya no se '
                   'puede deduplicar y se rechaza para no duplicar métricas históricas.'})


async def ingest(session, live: Live, event: EventIn, *, strict_age: bool = True,
                 store_detail: bool = True) -> dict:
    """Apply one event. strict_age rejects events older than the retention window (their
    idempotency keys may already be gone). The monitor bridge passes False because it
    tracks publication on the raw event itself."""
    if live.status == 'cancelled':
        raise HTTPException(409, 'El live fue cancelado.')
    at = event.timestamp or utcnow()
    if strict_age and event.timestamp is not None and aware_utc(event.timestamp) < (
            utcnow() - timedelta(days=settings.comments_retention_days)):
        raise too_old_error()
    if live.status == 'finished' and aware_utc(at) > aware_utc(live.ended_at) + LATE_EVENT_GRACE:
        raise HTTPException(409, 'El live ya terminó.')
    if live.status == 'scheduled':
        live.status, live.started_at = 'live', min(aware_utc(at), utcnow())
    if not await _claim_event(session, live.id, event.event_id):
        return {'accepted': False, 'duplicate': True, 'event_type': event.event_type}

    kind, new_phones, affected = event.event_type, 0, {live.id}
    if kind == 'comment':
        text = (event.text or '').strip()
        if not text or not event.username:
            raise HTTPException(422, 'Un comentario requiere username y text.')
        found = phones_in(text)
        interested = interested_in(text)
        first_interest = interested and await claim_interest(session, live.id, event.username)
        if store_detail:
            session.add(LiveComment(live_id=live.id, username=event.username, comment=text,
                                    phone_detected=found[0] if found else None,
                                    interested=interested, created_at=at))
        await _bump(session, live.id, 'comments_count', 1)
        if first_interest:
            await _bump(session, live.id, 'interested_viewers', 1)
        for phone in found:
            outcome, touched = await save_phone(session, live, phone, event.username,
                                                'comment', at)
            new_phones += outcome == 'new'
            affected |= touched
    elif kind in COUNTER:
        await _bump(session, live.id, COUNTER[kind], event.value)
    elif kind == 'viewer':
        # A sample of CONCURRENT viewers: feeds peak and average, never "unique viewers".
        await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live.id).values(
            peak_viewers=case((LiveMetrics.peak_viewers < event.value, event.value),
                              else_=LiveMetrics.peak_viewers),
            viewer_samples=LiveMetrics.viewer_samples + 1,
            viewer_sum=LiveMetrics.viewer_sum + event.value, updated_at=utcnow()))
    elif kind == 'unique_viewers':
        await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live.id).values(
            unique_viewers=case((LiveMetrics.unique_viewers.is_(None), event.value),
                                (LiveMetrics.unique_viewers < event.value, event.value),
                                else_=LiveMetrics.unique_viewers), updated_at=utcnow()))
    elif kind == 'interested':
        await _bump(session, live.id, 'interested_viewers', max(1, event.value))
    elif kind == 'direct_message':
        await _bump(session, live.id, 'direct_messages_count', max(1, event.value))
    else:  # phone_detected | phone_manual
        phone = normalize_phone(event.phone or event.text or '')
        if not phone:
            raise HTTPException(422, 'No se pudo reconocer un teléfono válido.')
        outcome, touched = await save_phone(session, live, phone, event.username,
                                            SOURCE_BY_EVENT[kind], at)
        new_phones += outcome == 'new'
        affected |= touched
    await refresh_many(session, live, affected)
    return {'accepted': True, 'duplicate': False, 'event_type': kind, 'phones_new': new_phones}


async def register_phone(session, live: Live, body) -> tuple[PhoneRegistry, str | None]:
    if live.status == 'cancelled':
        raise HTTPException(409, 'El live fue cancelado.')
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, 'Teléfono inválido.')
    outcome, affected = await save_phone(session, live, phone, body.tiktok_username,
                                         body.source, body.captured_at or utcnow())
    registry = await session.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == phone))
    await refresh_many(session, live, affected)
    return registry, outcome


async def finish_live(session, live: Live, ended_at, status) -> Live:
    if live.status in ('finished', 'cancelled'):
        return live  # idempotent
    end = ended_at or utcnow()
    if aware_utc(end) < aware_utc(live.started_at):
        raise HTTPException(422, 'ended_at no puede ser anterior al inicio.')
    live.ended_at, live.status, live.updated_at = end, status, utcnow()
    live.duration_seconds = int((aware_utc(end) - aware_utc(live.started_at)).total_seconds())
    await session.flush()
    await refresh_derived(session, live)
    return live


def contact_time_seconds(row) -> int | None:
    """Seconds from first capture to first contact."""
    if row.contacted_at is None:
        return None
    return max(0, int((aware_utc(row.contacted_at)
                       - aware_utc(row.first_captured_at)).total_seconds()))
