"""Bell notifications, alerts about suspicious contacts and "no me contactan" comments.

Two different audiences (the bell shows each one its own):
  * managers (supervisor, marketing head, manager): alerts and complaints, with phones, so they
    can find out what is happening with a person. Permission `alerts:read` / `alerts:review`.
  * sales agents: reminders about THEIR pending chats (10 / 20 minutes). They never see alerts."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...shared.db import get_session
from . import alerts, queries
from .leads import allowed, names_of
from .models import CapturedPhone, ContactAlert, Live, LiveComment, PhoneRegistry, TiktokAccount
from .security import require_scope
from .service import utcnow

router = APIRouter(prefix='/api', tags=['alerts'])
bell = require_scope('contacts:read', 'alerts:read')
manager = require_scope('alerts:read')
reviewer = require_scope('alerts:review')


@router.get('/notifications')
async def notifications(who=Depends(bell), session=Depends(get_session)):
    """What the bell shows. Each person receives only the sections her role allows."""
    out: dict = {'generated_at': queries.iso(utcnow()), 'agent': None, 'alerts': None, 'count': 0}
    if allowed(who, 'contacts:read'):
        agent = await alerts.agent_reminders(session, who['user_id'])
        out['agent'] = agent
        out['count'] += agent['mine_over_first'] + agent['unclaimed_waiting']
    if allowed(who, 'alerts:read'):
        open_alerts = (await alerts.open_counts(session))['alerts']
        complaints = await session.scalar(select(func.count()).select_from(LiveComment).where(
            LiveComment.complaint.is_(True), LiveComment.complaint_reviewed_at.is_(None))) or 0
        out['alerts'] = {'open': open_alerts, 'complaints_open': complaints}
        out['count'] += open_alerts + complaints
    return out


def alert_item(alert, contact, live, first_live, accounts, names):
    return {
        'id': alert.id, 'kind': alert.kind, 'kind_label': alerts.KIND_LABEL[alert.kind],
        'status': alert.status, 'repeats': alert.repeats, 'note': alert.note,
        'phone': contact.phone, 'tiktok_username': contact.first_username,
        'contact_status': contact.status,
        'advisor_id': alert.advisor_id, 'advisor': names.get(alert.advisor_id),
        'contacted_at': queries.iso(alert.contacted_at),
        'first_captured_at': queries.iso(contact.first_captured_at),
        'first_live_id': contact.first_live_id,
        'first_account': ('@' + accounts.get(contact.first_account_id, contact.first_account_id)
                          if contact.first_account_id else None),
        'live_id': alert.live_id, 'live_title': live.title if live else None,
        'account': '@' + accounts.get(alert.account_id, alert.account_id or ''),
        'comment_at': queries.iso(alert.comment_at),
        'last_seen_at': queries.iso(alert.last_seen_at),
        'minutes_after_contact': max(0, int((alert.comment_at - alert.contacted_at)
                                            .total_seconds() // 60)),
        'reviewed_by': names.get(alert.reviewed_by, alert.reviewed_by),
        'reviewed_at': queries.iso(alert.reviewed_at), 'created_at': queries.iso(alert.created_at)}


@router.get('/alerts')
async def list_alerts(status: Literal['open', 'reviewed', 'dismissed', 'all'] = 'open',
                      limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                      who=Depends(manager), session=Depends(get_session)):
    query = (select(ContactAlert, PhoneRegistry, Live)
             .join(PhoneRegistry, PhoneRegistry.id == ContactAlert.registry_id)
             .join(Live, Live.id == ContactAlert.live_id)
             .order_by(ContactAlert.last_seen_at.desc(), ContactAlert.id.desc()))
    if status != 'all':
        query = query.where(ContactAlert.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.execute(query.offset(offset).limit(limit))).all()
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    names = await names_of(session, {a.advisor_id for a, _, _ in rows}
                           | {a.reviewed_by for a, _, _ in rows})
    return {'items': [alert_item(a, c, live, None, accounts, names) for a, c, live in rows],
            'total': total, 'next_offset': offset + limit if offset + limit < total else None}


class AlertReview(BaseModel):
    status: Literal['open', 'reviewed', 'dismissed']
    note: str | None = Field(default=None, max_length=500)


@router.patch('/alerts/{alert_id}')
async def review_alert(alert_id: int, body: AlertReview, who=Depends(reviewer),
                       session=Depends(get_session)):
    row = await session.get(ContactAlert, alert_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Alerta no encontrada.')
    row.status = body.status
    row.note = (body.note or '').strip() or row.note
    row.reviewed_by, row.reviewed_at = (who['user_id'], utcnow()) if body.status != 'open' \
        else (None, None)
    await session.commit()
    contact = await session.get(PhoneRegistry, row.registry_id)
    live = await session.get(Live, row.live_id)
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    names = await names_of(session, {row.advisor_id, row.reviewed_by})
    return alert_item(row, contact, live, None, accounts, names)


@router.get('/complaints')
async def list_complaints(status: Literal['open', 'reviewed', 'all'] = 'open',
                          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                          who=Depends(manager), session=Depends(get_session)):
    """Comments such as "no me contactan". Rules find them; a person decides what they mean."""
    query = (select(LiveComment, Live).join(Live, Live.id == LiveComment.live_id)
             .where(LiveComment.complaint.is_(True))
             .order_by(LiveComment.created_at.desc(), LiveComment.id.desc()))
    if status == 'open':
        query = query.where(LiveComment.complaint_reviewed_at.is_(None))
    elif status == 'reviewed':
        query = query.where(LiveComment.complaint_reviewed_at.is_not(None))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.execute(query.offset(offset).limit(limit))).all()
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}

    def key(name):
        return (name or '').strip().lstrip('@').lower()

    users = {key(c.username) for c, _ in rows}
    # Who is this user? The contacts she (or someone with her TikTok name) left a number as.
    found: dict[str, dict[int, PhoneRegistry]] = {}
    if users:
        for username, contact in (await session.execute(
                select(CapturedPhone.tiktok_username, PhoneRegistry)
                .join(PhoneRegistry, PhoneRegistry.phone == CapturedPhone.phone)
                .where(func.lower(CapturedPhone.tiktok_username).in_(
                    users | {'@' + u for u in users})))).all():
            found.setdefault(key(username), {})[contact.id] = contact
    names = await names_of(session, {c.advisor_id for d in found.values() for c in d.values()}
                           | {c.complaint_reviewed_by for c, _ in rows})
    items = []
    for comment, live in rows:
        contacts = sorted(found.get(key(comment.username), {}).values(), key=lambda c: c.id)
        items.append({
            'id': comment.id, 'username': comment.username, 'comment': comment.comment,
            'created_at': queries.iso(comment.created_at), 'live_id': live.id,
            'live_title': live.title,
            'account': '@' + accounts.get(live.account_id, live.account_id),
            'contacts': [{'phone': c.phone, 'status': c.status,
                          'advisor': names.get(c.advisor_id), 'advisor_id': c.advisor_id,
                          'contacted_at': queries.iso(c.contacted_at)} for c in contacts],
            'reviewed_by': names.get(comment.complaint_reviewed_by, comment.complaint_reviewed_by),
            'reviewed_at': queries.iso(comment.complaint_reviewed_at)})
    return {'items': items, 'total': total,
            'next_offset': offset + limit if offset + limit < total else None}


class ComplaintReview(BaseModel):
    reviewed: bool = True


@router.patch('/complaints/{comment_id}')
async def review_complaint(comment_id: int, body: ComplaintReview, who=Depends(reviewer),
                           session=Depends(get_session)):
    row = await session.get(LiveComment, comment_id, with_for_update=True)
    if row is None or not row.complaint:
        raise HTTPException(404, 'Comentario no encontrado.')
    row.complaint_reviewed_by, row.complaint_reviewed_at = (
        (who['user_id'], utcnow()) if body.reviewed else (None, None))
    await session.commit()
    return {'id': row.id, 'reviewed': body.reviewed}
