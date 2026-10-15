"""Attention workflow for sales agents and supervisors (people authenticated with Clerk).

Everything is persisted on the contact (phone_registry) and audited, so assigning an advisor or
marking a contact survives a reload and is visible to every authorized person. The browser never
receives the capture (ingest) token and no role here can write events.

Permissions (granted by role, validated here):
  contacts:read        see unassigned contacts and the ones assigned to you
  contacts:read_all    see every contact (supervisors)
  contacts:claim       take an unassigned contact / release your own
  contacts:update      change the status of your contacts (first contact time is recorded)
  contacts:assign_any  assign or release contacts of other people (supervisors)"""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, union_all

from ...shared.db import get_session
from ..analytics.models import UserRole
from ..identity.roles import PERMISSIONS
from . import contacts as workflow
from . import queries
from .models import Live, LiveComment, PhoneRegistry, TiktokAccount
from .security import require_scope
from .service import aware_utc, utcnow

router = APIRouter(prefix='/api', tags=['contacts'])
SOURCE_LABEL = {'comment': 'Comentario LIVE', 'manual_capture': 'Captura manual',
                'direct_message': 'Mensaje directo', 'speech': 'Speech', 'other': 'Otro'}
STATUS_LABEL = {'new': 'Nuevo', 'contacted': 'Contactado', 'qualified': 'Calificado',
                'discarded': 'Descartado'}
COMMENT_WINDOW = timedelta(days=7)
reader = require_scope('contacts:read')
board_reader = require_scope('contacts:read', 'read')


def allowed(who, permission: str) -> bool:
    return who.get('kind') == 'user' and permission in PERMISSIONS.get(who.get('role'), set())


def require(who, permission: str):
    if not allowed(who, permission):
        raise HTTPException(403, 'Tu rol no permite esta operación.')


async def names_of(session, ids) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await session.scalars(select(UserRole).where(UserRole.user_id.in_(ids)))).all()
    return {r.user_id: r.display_name or r.user_id for r in rows}


def lead_item(contact, live, attribution, comment, names, me, accounts):
    host_id, host = queries.owner_of(attribution, contact, live)
    return {
        'kind': 'lead', 'id': contact.id, 'live_id': contact.first_live_id,
        'account': '@' + accounts.get(contact.first_account_id, contact.first_account_id or ''),
        'platform': 'TikTok', 'source': SOURCE_LABEL.get(contact.first_source, contact.first_source),
        'user': ('@' + contact.first_username.lstrip('@')) if contact.first_username else None,
        'liveHost': host, 'liveHostId': host_id,
        'message': comment.comment if comment else None, 'phone': contact.phone,
        'type': 'Paciente potencial', 'status': STATUS_LABEL[contact.status],
        'statusCode': contact.status,
        'ownerId': contact.advisor_id,
        'owner': names.get(contact.advisor_id) if contact.advisor_id else None,
        'isMine': bool(contact.advisor_id and contact.advisor_id == me),
        'enteredAt': queries.iso(contact.first_captured_at),
        'contactedAt': queries.iso(contact.contacted_at),
        'contactTimeSeconds': queries.contact_time_seconds(contact),
        'updatedAt': queries.iso(contact.updated_at)}


async def _first_comments(session, contacts):
    phones = {c.phone for c in contacts}
    if not phones:
        return {}
    rows = (await session.scalars(select(LiveComment).where(
        LiveComment.phone_detected.in_(phones)).order_by(LiveComment.created_at))).all()
    found: dict = {}
    for row in rows:
        found.setdefault((row.live_id, row.phone_detected), row)
    return {c.phone: found.get((c.first_live_id, c.phone)) for c in contacts}


async def _present(session, rows, me):
    """rows: [(PhoneRegistry, Live|None)] -> UI items."""
    contacts = [c for c, _ in rows]
    attribution = await queries.load_attribution(session)
    comments = await _first_comments(session, contacts)
    names = await names_of(session, {c.advisor_id for c in contacts})
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    return [lead_item(c, live, attribution, comments.get(c.phone), names, me, accounts)
            for c, live in rows]


@router.get('/inbox')
async def inbox(scope: Literal['all', 'mine', 'unassigned'] = 'all',
                phone_only: bool = False, limit: int = Query(100, ge=1, le=200),
                offset: int = Query(0, ge=0), exclude_discarded: bool = False,
                who=Depends(reader), session=Depends(get_session)):
    """Filter authorized rows before paging the combined stream in the database."""
    require(who, 'contacts:read')
    me = who['user_id']
    lead_ids = select(PhoneRegistry.id.label('row_id'),
                      PhoneRegistry.first_captured_at.label('at'))
    if not allowed(who, 'contacts:read_all'):
        lead_ids = lead_ids.where(or_(PhoneRegistry.advisor_id.is_(None),
                                      PhoneRegistry.advisor_id == me))
    if scope == 'mine':
        lead_ids = lead_ids.where(PhoneRegistry.advisor_id == me)
    elif scope == 'unassigned':
        lead_ids = lead_ids.where(PhoneRegistry.advisor_id.is_(None))
    if exclude_discarded:
        lead_ids = lead_ids.where(PhoneRegistry.status != 'discarded')
    stream = lead_ids
    if not phone_only and scope == 'all':
        plain_ids = select((-LiveComment.id).label('row_id'),
                           LiveComment.created_at.label('at')).where(
            LiveComment.phone_detected.is_(None),
            LiveComment.created_at >= utcnow() - COMMENT_WINDOW)
        stream = union_all(lead_ids, plain_ids)
    stream = stream.subquery()
    total = await session.scalar(select(func.count()).select_from(stream))
    ids = list((await session.scalars(select(stream.c.row_id)
        .order_by(stream.c.at.desc(), stream.c.row_id.desc())
        .offset(offset).limit(limit + 1))).all())
    has_more = len(ids) > limit
    ids = ids[:limit]
    contacts = (await session.execute(select(PhoneRegistry, Live)
        .outerjoin(Live, Live.id == PhoneRegistry.first_live_id)
        .where(PhoneRegistry.id.in_([i for i in ids if i > 0])))).all()
    items = await _present(session, contacts, me)
    comment_ids = [-i for i in ids if i < 0]
    if comment_ids:
        plain = (await session.execute(select(LiveComment, Live)
            .join(Live, Live.id == LiveComment.live_id)
            .where(LiveComment.id.in_(comment_ids)))).all()
        attribution = await queries.load_attribution(session)
        accounts = {a.id: a.username
                    for a in (await session.scalars(select(TiktokAccount))).all()}
        for comment, live in plain:
            host_id, host = attribution.owner(live.tiktoker_id)
            items.append({
                'kind': 'comment', 'id': -comment.id, 'live_id': comment.live_id,
                'account': '@' + accounts.get(live.account_id, live.account_id),
                'platform': 'TikTok', 'source': 'Comentario LIVE',
                'user': '@' + comment.username.lstrip('@'),
                'liveHost': host, 'liveHostId': host_id, 'message': comment.comment,
                'phone': None, 'type': 'Interesado' if comment.interested else 'Comentario',
                'status': 'Nuevo', 'statusCode': 'new', 'ownerId': None, 'owner': None,
                'isMine': False, 'enteredAt': queries.iso(comment.created_at),
                'contactedAt': None, 'contactTimeSeconds': None, 'updatedAt': None})
    by_id = {item['id']: item for item in items}
    return {'items': [by_id[i] for i in ids], 'me': me, 'total': total,
            'next_offset': offset + limit if has_more else None,
            'generated_at': queries.iso(utcnow())}


class ContactPatch(BaseModel):
    action: Literal['claim', 'release', 'assign'] | None = None
    advisor_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal['new', 'contacted', 'qualified', 'discarded'] | None = None
    # Optimistic concurrency: reject if someone else changed the contact since it was shown.
    expected_status: Literal['new', 'contacted', 'qualified', 'discarded'] | None = None
    expect_unassigned: bool = False


@router.patch('/leads/{contact_id}')
async def update_contact(contact_id: int, body: ContactPatch, who=Depends(reader),
                         session=Depends(get_session)):
    me = who['user_id']
    manager = allowed(who, 'contacts:assign_any')
    current = await session.get(PhoneRegistry, contact_id)
    if current is None:
        raise HTTPException(404, 'Contacto no encontrado.')
    if not allowed(who, 'contacts:read_all') and current.advisor_id not in (None, me):
        if body.action == 'claim' or body.expect_unassigned:
            # Someone else won the race for a contact this person saw as free.
            raise HTTPException(409, 'Este contacto ya fue tomado por otra persona.')
        raise HTTPException(404, 'Contacto no encontrado.')  # not authorized: do not reveal it
    if body.expect_unassigned and current.advisor_id not in (None, me):
        raise HTTPException(409, 'Este contacto ya fue tomado por otra persona.')

    action = body.action or ('assign' if body.advisor_id is not None else None)
    if action == 'claim':
        require(who, 'contacts:claim')
        await workflow.claim(session, contact_id, me)
    elif action == 'release':
        require(who, 'contacts:claim')
        await workflow.release(session, contact_id, me, manager=manager)
    elif action == 'assign':
        if body.advisor_id is None:
            raise HTTPException(422, 'Indica a quién asignar.')
        require(who, 'contacts:claim' if body.advisor_id == me else 'contacts:assign_any')
        await workflow.assign(session, contact_id, me, body.advisor_id, manager=manager)
    if body.status is not None:
        require(who, 'contacts:update')
        await workflow.set_status(session, contact_id, me, body.status,
                                  expected_status=body.expected_status, manager=manager)
    await session.commit()
    row = await session.get(PhoneRegistry, contact_id)
    live = await session.get(Live, row.first_live_id) if row.first_live_id else None
    (item,) = await _present(session, [(row, live)], me)
    return item


@router.get('/leads/summary')
async def summary(who=Depends(board_reader), session=Depends(get_session)):
    """Counts only: unassigned load and per-agent progress (no phones, no comments)."""
    rows = (await session.execute(
        select(PhoneRegistry.advisor_id, PhoneRegistry.status, func.count())
        .group_by(PhoneRegistry.advisor_id, PhoneRegistry.status))).all()
    names = await names_of(session, {r[0] for r in rows})
    agents: dict = {}
    unassigned = 0
    for advisor, status, count in rows:
        if advisor is None:
            unassigned += count if status == 'new' else 0
            continue
        a = agents.setdefault(advisor, {'id': advisor, 'name': names.get(advisor, advisor),
                                        'assigned': 0, 'pending': 0, 'contacted': 0})
        a['assigned'] += count
        if status == 'new':
            a['pending'] += count
        else:
            a['contacted'] += count
    for member in await team_members(session):
        agents.setdefault(member['id'], {**member, 'assigned': 0, 'pending': 0, 'contacted': 0})
    return {'unassigned': unassigned, 'agents': sorted(agents.values(), key=lambda a: a['name'])}


async def team_members(session) -> list[dict]:
    rows = (await session.scalars(select(UserRole).where(
        UserRole.role.in_(('agente_ventas', 'supervisor', 'tiktoker', 'care')))
        .order_by(UserRole.display_name, UserRole.user_id))).all()
    return [{'id': r.user_id, 'name': r.display_name or r.user_id, 'role': r.role} for r in rows]


@router.get('/team')
async def team(who=Depends(board_reader), session=Depends(get_session)):
    return {'items': await team_members(session)}


@router.get('/leads/{contact_id}/history')
async def history(contact_id: int, who=Depends(reader), session=Depends(get_session)):
    """Who did what to a contact (supervisors and people who can see all contacts)."""
    require(who, 'contacts:read_all')
    from .models import ContactAudit
    rows = (await session.scalars(select(ContactAudit).where(
        ContactAudit.registry_id == contact_id).order_by(ContactAudit.created_at,
                                                         ContactAudit.id))).all()
    names = await names_of(session, {r.actor for r in rows})
    return {'items': [{'actor': r.actor, 'actor_name': names.get(r.actor, r.actor),
                       'action': r.action, 'previous': r.previous, 'value': r.value,
                       'at': queries.iso(r.created_at)} for r in rows]}


__all__ = ['router', 'aware_utc']
