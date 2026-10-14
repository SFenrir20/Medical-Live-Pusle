"""Idempotent materialization. Assignment to shifts is queried by event time, not ingestion time."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from ..broadcasts.models import RawEvent
from ..shifts.service import lock
from .classify import interested_in, phones_in
from .models import EventFact, Lead, LeadAlias, LeadPhone


def number(value, default=0):
    try:
        return max(0, min(int(value), 2_000_000_000))
    except (ValueError, TypeError):
        return default


async def contact_for(session, user_key, username, phones):
    # Serialize alias/phone resolution so concurrent events cannot create duplicate people.
    await lock(session, 'contacts')
    alias = await session.get(LeadAlias, user_key) if user_key else None
    existing = (await session.scalars(select(LeadPhone).where(LeadPhone.phone.in_(phones)))).all()
    lead_id = alias.lead_id if alias else existing[0].lead_id if existing else str(uuid4())
    lead = await session.get(Lead, lead_id)
    if lead is None:
        lead = Lead(id=lead_id, status='new', review_needed=False)
        session.add(lead)
        await session.flush()
    if user_key and alias is None:
        session.add(LeadAlias(user_key=user_key, lead_id=lead_id, username=username))
    for phone in phones:
        known = next((row for row in existing if row.phone == phone), None)
        if known is None:
            session.add(LeadPhone(phone=phone, lead_id=lead_id))
        elif known.lead_id != lead_id:
            # Shared/family numbers do not authorize silently merging two identities.
            lead.review_needed = True
            other = await session.get(Lead, known.lead_id)
            other.review_needed = True
    await session.flush()
    return lead_id


async def handle_event(session, event_id):
    row = await session.scalar(select(RawEvent).where(RawEvent.event_id == event_id)
                               .with_for_update())
    if row is None:
        return {'status': 'unknown-event', 'deduped': False}
    if await session.get(EventFact, row.event_id):
        return {'status': 'already-processed', 'deduped': True}
    if row.broadcast_id is None:
        return {'status': 'unlinked', 'deduped': False}
    data = row.payload or {}
    user = str(data.get('user') or '')[:128] or None
    text = row.raw_text or ''
    phones = phones_in(text) if row.type == 'comment' else []
    interest = interested_in(text) if row.type == 'comment' else False
    lead_id = await contact_for(session, user, data.get('username'), phones) \
        if (phones or interest) and (user or phones) else None
    final_gift = row.type == 'gift' and (number(data.get('gift_type')) != 1
                                        or number(data.get('repeat_end')) == 1)
    quantity = max(1, number(data.get('repeat_count'), 1)) if final_gift else 0
    fact = EventFact(event_id=row.event_id, broadcast_id=row.broadcast_id,
        account_id=row.account_id, user_key=user, kind=row.type, occurred_at=row.occurred_at,
        comments=int(row.type == 'comment'), likes=number(data.get('count'))
        if row.type == 'like' else 0, shares=int(row.type == 'share'), gifts=quantity,
        diamonds=min(2_000_000_000, quantity * number(data.get('diamond_count'))),
        viewers=number(data['viewers']) if row.type == 'audience'
        and data.get('viewers') is not None else None,
        interested=interest, phones=phones, lead_id=lead_id)
    session.add(fact)
    row.processed_at = datetime.now(timezone.utc)
    await session.flush()
    return {'status': 'processed', 'deduped': False}
