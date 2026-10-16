"""Suspicious contacts and reminders.

Detection (called while events are ingested, so it uses the contact's state AT THAT MOMENT):

  A contact still "new" that sends its number again is just insisting: no alert.
  A contact already marked contacted (or qualified) that sends the number again:
    - in the SAME live, once `alert_same_live_minutes` have passed since it was marked
                                                              -> same_live
    - in ANOTHER live of the same account (after being marked) -> other_live
    - in a live of ANOTHER account (after being marked)        -> other_account
  It means either the contact was marked without really being attended or the person was not
  helped. It is a reason to look, not proof. One alert per (contact, live); repeats count.

Reminders are for sales agents about their own pending chats and are NOT alerts."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...shared.config import settings
from .models import ContactAlert, PhoneRegistry
from .service import aware_utc, utcnow

CONTACTED = ('contacted', 'qualified')
KIND_LABEL = {'same_live': 'Mismo LIVE', 'other_live': 'Otro LIVE', 'other_account': 'Otra cuenta'}


async def check_reappearance(session, live, phone: str, at, outcome) -> ContactAlert | None:
    """Open (or reinforce) an alert if `phone` re-sent its number after being contacted."""
    if outcome == 'new':
        return None
    contact = await session.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == phone))
    if contact is None or contact.status not in CONTACTED or contact.contacted_at is None:
        return None
    at, marked = aware_utc(at), aware_utc(contact.contacted_at)
    if at <= marked:
        return None  # it wrote before anyone marked it: that is not a contradiction
    if contact.first_live_id == live.id:
        if at < marked + timedelta(minutes=settings.alert_same_live_minutes):
            return None
        kind = 'same_live'
    elif contact.first_account_id and contact.first_account_id != live.account_id:
        kind = 'other_account'
    else:
        kind = 'other_live'
    existing = await session.scalar(select(ContactAlert).where(
        ContactAlert.registry_id == contact.id, ContactAlert.live_id == live.id))
    if existing is not None:
        existing.repeats += 1
        existing.last_seen_at = max(aware_utc(existing.last_seen_at), at)
        return existing
    alert = ContactAlert(registry_id=contact.id, live_id=live.id, account_id=live.account_id,
                         kind=kind, comment_at=at, contacted_at=marked,
                         advisor_id=contact.advisor_id, last_seen_at=at, status='open')
    try:
        async with session.begin_nested():
            session.add(alert)
            await session.flush()
    except IntegrityError:  # a concurrent writer opened it first
        racer = await session.scalar(select(ContactAlert).where(
            ContactAlert.registry_id == contact.id, ContactAlert.live_id == live.id))
        if racer is not None:
            racer.repeats += 1
        return racer
    return alert


async def open_counts(session) -> dict:
    alerts = await session.scalar(select(func.count()).select_from(ContactAlert).where(
        ContactAlert.status == 'open')) or 0
    return {'alerts': alerts}


async def agent_reminders(session, user_id: str, now=None) -> dict:
    """Pending chats of ONE agent, by how long she has had them, plus unclaimed ones."""
    now = now or utcnow()
    first = now - timedelta(minutes=settings.reminder_first_minutes)
    second = now - timedelta(minutes=settings.reminder_second_minutes)
    mine = (await session.execute(
        select(PhoneRegistry.assigned_at, PhoneRegistry.first_captured_at).where(
            PhoneRegistry.advisor_id == user_id, PhoneRegistry.status == 'new'))).all()
    waiting = [aware_utc(assigned or captured) for assigned, captured in mine]
    unclaimed = (await session.execute(select(PhoneRegistry.first_captured_at).where(
        PhoneRegistry.advisor_id.is_(None), PhoneRegistry.status == 'new'))).scalars().all()
    return {
        'mine_pending': len(waiting),
        'mine_over_first': sum(w <= first for w in waiting),
        'mine_over_second': sum(w <= second for w in waiting),
        'unclaimed_waiting': sum(aware_utc(c) <= first for c in unclaimed),
        'first_minutes': settings.reminder_first_minutes,
        'second_minutes': settings.reminder_second_minutes,
        'oldest_minutes': (int((now - min(waiting)).total_seconds() // 60) if waiting else None),
    }
