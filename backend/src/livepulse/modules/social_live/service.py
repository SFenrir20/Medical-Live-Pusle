"""Ingestion rules. Counters are consolidated in live_metrics as events arrive, so dashboards
never count raw comments. Portable SQL: increments are atomic UPDATEs, duplicates are detected
with a savepoint instead of dialect-specific upserts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import phonenumbers
from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from ..analytics.classify import interested_in, phones_in
from .models import (
    CapturedPhone,
    Live,
    LiveComment,
    LiveEventKey,
    LiveMetrics,
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


async def create_live(session, body) -> tuple[Live, bool]:
    now = utcnow()
    if body.live_id:
        existing = await session.get(Live, body.live_id)
        if existing is not None:
            if (existing.tiktoker_id, existing.account_id) != (body.tiktoker_id, body.account_id):
                raise HTTPException(409, 'Ese live_id ya existe con otro TikToker o cuenta.')
            return existing, False
    tiktoker = await session.get(Tiktoker, body.tiktoker_id)
    account = await session.get(TiktokAccount, body.account_id)
    if tiktoker is None or not tiktoker.active:
        raise HTTPException(422, 'TikToker inexistente o inactivo.')
    if account is None or not account.active:
        raise HTTPException(422, 'Cuenta TikTok inexistente o inactiva.')
    live = Live(id=body.live_id or 'LIVE-' + uuid4().hex[:10].upper(),
                tiktoker_id=body.tiktoker_id, account_id=body.account_id,
                started_at=body.started_at or now, status=body.status,
                created_at=now, updated_at=now)
    session.add(live)
    session.add(LiveMetrics(live_id=live.id, created_at=now, updated_at=now))
    await session.flush()
    return live, True


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


async def _bump(session, live_id, column, amount):
    if amount <= 0:
        return
    await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live_id).values(
        **{column: getattr(LiveMetrics, column) + amount, 'updated_at': utcnow()}))


async def save_phone(session, live_id, phone, username, source, captured_at) -> bool:
    try:
        async with session.begin_nested():
            session.add(CapturedPhone(live_id=live_id, phone=phone, tiktok_username=username,
                                      source=source, captured_at=captured_at, status='new'))
            await session.flush()
    except IntegrityError:
        return False  # the same number in the same live is one lead
    return True


async def refresh_derived(session, live: Live):
    """phones_captured and leads_per_hour come from the stored rows, not from increments."""
    phones = await session.scalar(select(func.count()).select_from(CapturedPhone)
                                  .where(CapturedPhone.live_id == live.id)) or 0
    end = live.ended_at or utcnow()
    seconds = max(60.0, (aware_utc(end) - aware_utc(live.started_at)).total_seconds())
    await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live.id).values(
        phones_captured=phones, leads_per_hour=round(phones / (seconds / 3600), 2),
        updated_at=utcnow()))


async def ingest(session, live: Live, event: EventIn) -> dict:
    if live.status == 'cancelled':
        raise HTTPException(409, 'El live fue cancelado.')
    at = event.timestamp or utcnow()
    if live.status == 'finished' and aware_utc(at) > aware_utc(live.ended_at) + LATE_EVENT_GRACE:
        raise HTTPException(409, 'El live ya terminó.')
    if live.status == 'scheduled':
        live.status, live.started_at = 'live', min(aware_utc(at), utcnow())
    if not await _claim_event(session, live.id, event.event_id):
        return {'accepted': False, 'duplicate': True, 'event_type': event.event_type}

    kind, phones_found = event.event_type, 0
    if kind == 'comment':
        text = (event.text or '').strip()
        if not text or not event.username:
            raise HTTPException(422, 'Un comentario requiere username y text.')
        found = phones_in(text)
        interested = interested_in(text)
        first_interest = interested and not await session.scalar(
            select(LiveComment.id).where(LiveComment.live_id == live.id,
                                         LiveComment.username == event.username,
                                         LiveComment.interested.is_(True)).limit(1))
        session.add(LiveComment(live_id=live.id, username=event.username, comment=text,
                                phone_detected=found[0] if found else None,
                                interested=interested, created_at=at))
        await _bump(session, live.id, 'comments_count', 1)
        if first_interest:
            await _bump(session, live.id, 'interested_viewers', 1)
        for phone in found:
            phones_found += await save_phone(session, live.id, phone, event.username,
                                             'comment', at)
    elif kind in COUNTER:
        await _bump(session, live.id, COUNTER[kind], event.value)
    elif kind == 'viewer':
        await session.execute(update(LiveMetrics).where(LiveMetrics.live_id == live.id).values(
            unique_viewers=case((LiveMetrics.unique_viewers < event.value, event.value),
                                else_=LiveMetrics.unique_viewers), updated_at=utcnow()))
    elif kind == 'interested':
        await _bump(session, live.id, 'interested_viewers', max(1, event.value))
    elif kind == 'direct_message':
        await _bump(session, live.id, 'direct_messages_count', max(1, event.value))
    else:  # phone_detected | phone_manual
        phone = normalize_phone(event.phone or event.text or '')
        if not phone:
            raise HTTPException(422, 'No se pudo reconocer un teléfono válido.')
        phones_found += await save_phone(session, live.id, phone, event.username,
                                         SOURCE_BY_EVENT[kind], at)
    await refresh_derived(session, live)
    return {'accepted': True, 'duplicate': False, 'event_type': kind,
            'phones_new': phones_found}


async def register_phone(session, live: Live, body) -> tuple[CapturedPhone, bool]:
    if live.status == 'cancelled':
        raise HTTPException(409, 'El live fue cancelado.')
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, 'Teléfono inválido.')
    captured_at = body.captured_at or utcnow()
    created = await save_phone(session, live.id, phone, body.tiktok_username, body.source,
                               captured_at)
    row = await session.scalar(select(CapturedPhone).where(
        CapturedPhone.live_id == live.id, CapturedPhone.phone == phone))
    await refresh_derived(session, live)
    return row, created


async def update_phone(session, phone_id: int, body) -> CapturedPhone:
    row = await session.get(CapturedPhone, phone_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Teléfono no encontrado.')
    now = utcnow()
    if body.status is not None:
        row.status = body.status
        if body.status != 'new' and row.contacted_at is None and body.status != 'discarded':
            row.contacted_at = body.contacted_at or now
    if body.contacted_at is not None and row.contacted_at is None:
        row.contacted_at = body.contacted_at
    if body.advisor_id is not None:
        row.advisor_id = body.advisor_id
    if row.contacted_at is not None and aware_utc(row.contacted_at) < aware_utc(row.captured_at):
        raise HTTPException(422, 'contacted_at no puede ser anterior a la captura.')
    row.updated_at = now
    return row


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
    if row.contacted_at is None:
        return None
    return max(0, int((aware_utc(row.contacted_at) - aware_utc(row.captured_at)).total_seconds()))
