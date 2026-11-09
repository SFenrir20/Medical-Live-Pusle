"""CRM over the WhatsApp conversations: the inbox list and detail with stage, tags, notes,
consent, owner and scheduled messages; the contacts table; and the pre-written messages.

Who can do what (the same ownership rules as the WhatsApp mirror):
  * everyone with `wa:read` sees what the mirror lets them see (own and free conversations;
    supervisors, marketing head and manager see all);
  * changing anything about a conversation needs it to be yours (or `contacts:assign_any`, the
    supervisor); a free one must be taken first; marketing head and manager only review;
  * managing the pre-written messages is `crm:manage` (supervisor, admin).
The stage of a LIVE contact is the contact's own status, so there is a single truth in the app."""
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_, select

from ...shared.config import settings
from ...shared.db import get_session
from ..automation.models import Broadcast, Flow
from ..chat.models import ChatConversation, ChatMessage, OptOut
from ..chat.service import aware, utcnow
from ..identity.roles import permissions_of
from ..social_live import contacts as workflow
from ..social_live import queries
from ..social_live.leads import _first_comments, names_of, team_members
from ..social_live.models import CapturedPhone, PhoneRegistry
from ..social_live.security import require_scope
from ..whatsapp import api as wa_api
from ..whatsapp import service as wa
from . import funnels, sites
from .models import ChatConsent, ChatNote, ChatScheduled, QuickReply, Site

router = APIRouter(prefix='/api/crm', tags=['crm'])
reader = require_scope('wa:read')
manager = require_scope('crm:manage')

STAGES = ('new', 'contacted', 'qualified', 'discarded')
RESULTS = ('agendo', 'no_interesado', 'sin_respuesta', 'numero_equivocado')
LIMA = timezone(timedelta(hours=-5))
SHORTCUT = re.compile(r'^[a-z0-9_-]{2,30}$')


def perms(who) -> set[str]:
    return permissions_of(who.get('role'))


def owner_of(conversation, registry):
    return registry.advisor_id if registry else conversation.advisor_id


def stage_of(conversation, registry) -> str:
    return registry.status if registry else conversation.stage


def iso(value):
    return queries.iso(aware(value)) if value is not None else None


# ---- visibility and permissions ----------------------------------------------------------

def owner_expr():
    return case((PhoneRegistry.id.is_not(None), PhoneRegistry.advisor_id),
                else_=ChatConversation.advisor_id)


def visible_conversations(who):
    """Conversations of the WhatsApp channel this person may see, with their contact (if any)."""
    query = select(ChatConversation, PhoneRegistry).outerjoin(
        PhoneRegistry, PhoneRegistry.phone == ChatConversation.phone).where(
        ChatConversation.channel_id == wa.CHANNEL)
    if 'wa:read_all' not in perms(who):
        query = query.where(sites.visible_to(who['user_id'], owner_expr()))
    return query


async def writable(session, conversation_id: int, who):
    """The conversation, only if this person may change it. Raises with the reason otherwise."""
    p = perms(who)
    if 'wa:send' not in p and 'contacts:assign_any' not in p:
        raise HTTPException(403, 'Tu rol solo revisa las conversaciones.')
    conversation, registry = await wa_api.access(session, conversation_id, who)
    if owner_of(conversation, registry) != who['user_id'] and 'contacts:assign_any' not in p:
        raise HTTPException(409, 'Toma el contacto antes de editarlo. Si lo tiene otra asesora, '
                                 'debe reasignarlo un supervisor.')
    return conversation, registry


# ---- presentation -------------------------------------------------------------------------

def message_preview(message) -> dict | None:
    if message is None:
        return None
    kind = message.media_kind if message.media_kind != 'none' else None
    if message.media_id and kind is None:
        kind = 'image'
    return {'body': message.body[:140], 'direction': message.direction, 'status': message.status,
            'at': iso(message.created_at), 'kind': kind, 'seconds': message.media_seconds,
            'name': message.media_name}


async def build_items(session, rows, who) -> list[dict]:
    """One batch of lookups for a page of conversations (no query per row)."""
    ids = [c.id for c, _ in rows]
    phones = [c.phone for c, _ in rows]
    last: dict[int, ChatMessage] = {}
    consent, opted, lives = {}, set(), {}
    if ids:
        latest = dict((await session.execute(
            select(ChatMessage.conversation_id, func.max(ChatMessage.id)).where(
                ChatMessage.conversation_id.in_(ids)).group_by(ChatMessage.conversation_id))).all())
        if latest:
            found = {m.id: m for m in (await session.scalars(select(ChatMessage).where(
                ChatMessage.id.in_(list(latest.values()))))).all()}
            last = {cid: found.get(mid) for cid, mid in latest.items()}
        consent = {c.phone: c.status for c in (await session.scalars(select(ChatConsent).where(
            ChatConsent.phone.in_(phones)))).all()}
        opted = set((await session.scalars(select(OptOut.phone).where(
            OptOut.phone.in_(phones)))).all())
        lives = dict((await session.execute(select(CapturedPhone.phone, func.count()).where(
            CapturedPhone.phone.in_(phones)).group_by(CapturedPhone.phone))).all())
    names = await names_of(session, {owner_of(c, r) for c, r in rows})
    site_ids = {c.site_id for c, _ in rows if c.site_id}
    site_names = dict((await session.execute(select(Site.id, Site.name).where(
        Site.id.in_(site_ids)))).all()) if site_ids else {}
    me = who['user_id']
    items = []
    for conversation, registry in rows:
        owner = owner_of(conversation, registry)
        status = consent.get(conversation.phone, 'unknown')
        items.append({
            'id': conversation.id, 'phone': conversation.phone,
            'name': conversation.contact_name or (registry.first_username if registry else None),
            'registry_id': registry.id if registry else None,
            'advisor_id': owner, 'advisor_name': names.get(owner) if owner else None,
            'is_mine': owner == me, 'stage': stage_of(conversation, registry),
            'result': conversation.result, 'tags': conversation.tags or [],
            'archived': conversation.archived, 'unread': conversation.unread,
            'last_message_at': iso(conversation.last_message_at),
            'last': message_preview(last.get(conversation.id)),
            'waiting': bool(last.get(conversation.id) and last[conversation.id].direction == 'in'),
            'consent': status, 'opted_out': conversation.phone in opted,
            'origin': 'tiktok_live' if registry else 'whatsapp',
            'site': site_names.get(conversation.site_id),
            'appointment_at': iso(conversation.appointment_at),
            'appointment_label': conversation.appointment_label,
            'lives': lives.get(conversation.phone, 0)})
    return items


SCOPES = ('all', 'mine', 'unread', 'waiting', 'unassigned', 'archived')


def last_direction():
    """Direction of the newest message: 'in' means the person is waiting for an answer."""
    return (select(ChatMessage.direction).where(ChatMessage.conversation_id == ChatConversation.id)
            .order_by(ChatMessage.id.desc()).limit(1).correlate(ChatConversation).scalar_subquery())


def in_scope(query, scope: str, me: str):
    if scope == 'archived':
        return query.where(ChatConversation.archived.is_(True))
    query = query.where(ChatConversation.archived.is_(False))
    if scope == 'mine':
        query = query.where(owner_expr() == me)
    elif scope == 'unread':
        query = query.where(ChatConversation.unread > 0)
    elif scope == 'waiting':
        query = query.where(last_direction() == 'in')
    elif scope == 'unassigned':
        query = query.where(owner_expr().is_(None))
    return query


def matching(query, text: str):
    needle = text.strip().lower()[:100]
    if not needle:
        return query
    in_message = exists(select(ChatMessage.id).where(
        ChatMessage.conversation_id == ChatConversation.id,
        func.lower(ChatMessage.body).contains(needle, autoescape=True)))
    return query.where(or_(
        ChatConversation.phone.contains(needle, autoescape=True),
        func.lower(func.coalesce(ChatConversation.contact_name, '')).contains(needle, autoescape=True),
        func.lower(func.coalesce(PhoneRegistry.first_username, '')).contains(needle, autoescape=True),
        in_message))


@router.get('/conversations')
async def conversations(scope: Literal['all', 'mine', 'unread', 'waiting', 'unassigned', 'archived'] = 'all',
                        q: str = Query('', max_length=100), offset: int = Query(0, ge=0),
                        who=Depends(reader), session=Depends(get_session)):
    me = who['user_id']
    base = visible_conversations(who)
    rows = (await session.execute(matching(in_scope(base, scope, me), q).order_by(
        ChatConversation.last_message_at.desc().nullslast(), ChatConversation.id.desc())
        .offset(offset).limit(51))).all()
    counts = {}
    for name in SCOPES:
        counts[name] = await session.scalar(select(func.count()).select_from(
            in_scope(base, name, me).subquery())) or 0
    return {'items': await build_items(session, rows[:50], who), 'has_more': len(rows) > 50,
            'counts': counts}


async def detail_of(session, conversation, registry, who) -> dict:
    (item,) = await build_items(session, [(conversation, registry)], who)
    notes = (await session.scalars(select(ChatNote).where(
        ChatNote.conversation_id == conversation.id).order_by(ChatNote.id.desc()).limit(50))).all()
    scheduled = (await session.scalars(select(ChatScheduled).where(
        ChatScheduled.conversation_id == conversation.id, ChatScheduled.status != 'cancelled')
        .order_by(ChatScheduled.send_at.desc()).limit(30))).all()
    names = await names_of(session, {n.author_id for n in notes} | {s.author_id for s in scheduled})
    consent = await session.get(ChatConsent, conversation.phone)
    return {**item,
            'notes': [{'id': n.id, 'body': n.body, 'author_id': n.author_id,
                       'author_name': names.get(n.author_id, n.author_id),
                       'at': iso(n.created_at)} for n in notes],
            'scheduled': [{'id': s.id, 'body': s.body, 'send_at': iso(s.send_at), 'status': s.status,
                           'detail': s.detail, 'author_name': names.get(s.author_id, s.author_id)}
                          for s in scheduled],
            'consent_note': consent.note if consent else None,
            'consent_at': iso(consent.changed_at) if consent else None,
            'can_edit': owner_of(conversation, registry) == who['user_id']
            or 'contacts:assign_any' in perms(who)}


@router.get('/conversations/{conversation_id}')
async def detail(conversation_id: int, who=Depends(reader), session=Depends(get_session)):
    conversation, registry = await wa_api.access(session, conversation_id, who)
    return await detail_of(session, conversation, registry, who)


async def set_stage(session, conversation, registry, who, stage: str) -> None:
    """Change the stage of the contact (its own status for a LIVE contact) and log the move in the
    built-in funnel. The caller already checked that this person may edit the conversation."""
    before = stage_of(conversation, registry)
    if registry:
        await workflow.set_status(session, registry.id, who['user_id'], stage,
                                  manager='contacts:assign_any' in perms(who))
        await session.refresh(registry)
    else:
        conversation.stage = stage
    await funnels.record_contact_stage(session, conversation.id, before,
                                       stage_of(conversation, registry), who['user_id'])


class ConversationPatch(BaseModel):
    stage: Literal['new', 'contacted', 'qualified', 'discarded'] | None = None
    result: str | None = Field(default=None, max_length=20)   # '' clears it
    tags: list[str] | None = Field(default=None, max_length=20)
    archived: bool | None = None


@router.patch('/conversations/{conversation_id}')
async def patch(conversation_id: int, body: ConversationPatch, who=Depends(reader),
                session=Depends(get_session)):
    conversation, registry = await writable(session, conversation_id, who)
    if body.stage is not None:
        await set_stage(session, conversation, registry, who, body.stage)
    if body.result is not None:
        if body.result and body.result not in RESULTS:
            raise HTTPException(422, 'Resultado no válido.')
        conversation.result = body.result or None
    if body.tags is not None:
        conversation.tags = sorted({t.strip()[:30] for t in body.tags if t.strip()})
    if body.archived is not None:
        conversation.archived = body.archived
    await session.commit()
    return await detail_of(session, conversation, registry, who)


@router.post('/conversations/{conversation_id}/unread')
async def mark_unread(conversation_id: int, who=Depends(reader), session=Depends(get_session)):
    conversation, registry = await writable(session, conversation_id, who)
    conversation.unread = max(conversation.unread or 0, 1)
    await session.commit()
    return await detail_of(session, conversation, registry, who)


class AssignIn(BaseModel):
    advisor_id: str | None = Field(default=None, min_length=1, max_length=64)


@router.post('/conversations/{conversation_id}/assign')
async def assign(conversation_id: int, body: AssignIn, who=Depends(reader),
                 session=Depends(get_session)):
    """Hand the conversation (and its contact) to another person, or release it. Supervisors."""
    if 'contacts:assign_any' not in perms(who):
        raise HTTPException(403, 'Solo un supervisor puede reasignar.')
    conversation, registry = await wa_api.access(session, conversation_id, who)
    if body.advisor_id and body.advisor_id not in {m['id'] for m in await team_members(session)}:
        raise HTTPException(422, 'Esa persona no es del equipo de atención.')
    if registry:
        if body.advisor_id:
            await workflow.assign(session, registry.id, who['user_id'], body.advisor_id, manager=True)
        else:
            await workflow.release(session, registry.id, who['user_id'], manager=True)
        await session.refresh(registry)
    else:
        conversation.advisor_id = body.advisor_id
    await session.commit()
    return await detail_of(session, conversation, registry, who)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post('/conversations/{conversation_id}/notes', status_code=201)
async def add_note(conversation_id: int, body: NoteIn, who=Depends(reader),
                   session=Depends(get_session)):
    conversation, registry = await writable(session, conversation_id, who)
    text = body.body.strip()
    if not text:
        raise HTTPException(422, 'Escribe la nota.')
    session.add(ChatNote(conversation_id=conversation.id, author_id=who['user_id'], body=text,
                         created_at=utcnow()))
    await session.commit()
    return await detail_of(session, conversation, registry, who)


@router.delete('/notes/{note_id}')
async def delete_note(note_id: int, who=Depends(reader), session=Depends(get_session)):
    note = await session.get(ChatNote, note_id)
    if note is None:
        raise HTTPException(404, 'Nota no encontrada.')
    conversation, registry = await wa_api.access(session, note.conversation_id, who)
    if note.author_id != who['user_id'] and 'contacts:assign_any' not in perms(who):
        raise HTTPException(403, 'Solo quien escribió la nota o un supervisor puede borrarla.')
    await session.delete(note)
    await session.commit()
    return await detail_of(session, conversation, registry, who)


class ScheduleIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    send_at: datetime


@router.post('/conversations/{conversation_id}/scheduled', status_code=201)
async def schedule(conversation_id: int, body: ScheduleIn, who=Depends(reader),
                   session=Depends(get_session)):
    """Only the person who owns the contact can schedule a message to it."""
    if 'wa:send' not in perms(who):
        raise HTTPException(403, 'Tu rol no puede enviar mensajes.')
    conversation, registry = await wa_api.access(session, conversation_id, who, own=True)
    send_at = body.send_at if body.send_at.tzinfo else body.send_at.replace(tzinfo=LIMA)
    now = utcnow()
    if not now + timedelta(seconds=30) <= send_at <= now + timedelta(days=30):
        raise HTTPException(422, 'Programa el mensaje entre dentro de 1 minuto y 30 días.')
    if not body.text.strip():
        raise HTTPException(422, 'Escribe el mensaje.')
    session.add(ChatScheduled(conversation_id=conversation.id, author_id=who['user_id'],
                              body=body.text.strip(), send_at=send_at.astimezone(timezone.utc),
                              status='pending', created_at=now))
    await session.commit()
    return await detail_of(session, conversation, registry, who)


@router.delete('/scheduled/{scheduled_id}')
async def cancel_scheduled(scheduled_id: int, who=Depends(reader), session=Depends(get_session)):
    item = await session.get(ChatScheduled, scheduled_id, with_for_update=True)
    if item is None:
        raise HTTPException(404, 'Mensaje programado no encontrado.')
    conversation, registry = await wa_api.access(session, item.conversation_id, who)
    if item.author_id != who['user_id'] and 'contacts:assign_any' not in perms(who):
        raise HTTPException(403, 'Solo quien lo programó o un supervisor puede cancelarlo.')
    if item.status != 'pending':
        raise HTTPException(409, 'Ese mensaje ya salió o se canceló.')
    item.status, item.detail = 'cancelled', 'Cancelado por una persona.'
    await session.commit()
    return await detail_of(session, conversation, registry, who)


class ConsentIn(BaseModel):
    status: Literal['granted', 'revoked']
    note: str | None = Field(default=None, max_length=200)


@router.put('/conversations/{conversation_id}/consent')
async def consent(conversation_id: int, body: ConsentIn, who=Depends(reader),
                  session=Depends(get_session)):
    """Whether the person agreed to receive WhatsApp messages. Revoking also puts her on the
    opt-out list, so no bot or campaign writes to her again."""
    conversation, registry = await writable(session, conversation_id, who)
    opted = await session.get(OptOut, conversation.phone)
    if body.status == 'granted' and opted is not None:
        raise HTTPException(409, 'La persona pidió no recibir mensajes: no se puede marcar como '
                                 'autorizada desde aquí.')
    row = await session.get(ChatConsent, conversation.phone)
    now = utcnow()
    if row is None:
        row = ChatConsent(phone=conversation.phone, status=body.status, changed_by=who['user_id'],
                          changed_at=now)
        session.add(row)
    row.status, row.note = body.status, (body.note or '').strip()[:200] or None
    row.changed_by, row.changed_at = who['user_id'], now
    if body.status == 'revoked' and opted is None:
        session.add(OptOut(phone=conversation.phone, reason='Revocado por el equipo de atención'))
    await session.commit()
    return await detail_of(session, conversation, registry, who)


# ---- pre-written messages -------------------------------------------------------------------

class QuickReplyIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    shortcut: str = Field(min_length=2, max_length=30)
    body: str = Field(min_length=1, max_length=4000)
    active: bool = True


def quick_item(reply: QuickReply) -> dict:
    return {'id': reply.id, 'title': reply.title, 'shortcut': reply.shortcut, 'body': reply.body,
            'active': reply.active}


@router.get('/quick-replies')
async def quick_replies(all: bool = False, who=Depends(reader), session=Depends(get_session)):
    query = select(QuickReply).order_by(QuickReply.title)
    if not (all and 'crm:manage' in perms(who)):
        query = query.where(QuickReply.active.is_(True))
    return {'items': [quick_item(r) for r in (await session.scalars(query)).all()]}


def clean_shortcut(value: str) -> str:
    shortcut = value.strip().lower().lstrip('/')
    if not SHORTCUT.match(shortcut):
        raise HTTPException(422, 'El atajo usa 2 a 30 letras minúsculas, números, - o _.')
    return shortcut


@router.post('/quick-replies', status_code=201)
async def create_quick_reply(body: QuickReplyIn, who=Depends(manager), session=Depends(get_session)):
    shortcut = clean_shortcut(body.shortcut)
    if await session.scalar(select(QuickReply.id).where(QuickReply.shortcut == shortcut)):
        raise HTTPException(409, 'Ya existe un mensaje con ese atajo.')
    reply = QuickReply(title=body.title.strip(), shortcut=shortcut, body=body.body.strip(),
                       active=body.active, created_by=who['user_id'], created_at=utcnow())
    session.add(reply)
    await session.commit()
    return quick_item(reply)


@router.put('/quick-replies/{reply_id}')
async def update_quick_reply(reply_id: int, body: QuickReplyIn, who=Depends(manager),
                             session=Depends(get_session)):
    reply = await session.get(QuickReply, reply_id)
    if reply is None:
        raise HTTPException(404, 'Mensaje no encontrado.')
    shortcut = clean_shortcut(body.shortcut)
    clash = await session.scalar(select(QuickReply.id).where(
        QuickReply.shortcut == shortcut, QuickReply.id != reply_id))
    if clash:
        raise HTTPException(409, 'Ya existe un mensaje con ese atajo.')
    reply.title, reply.shortcut = body.title.strip(), shortcut
    reply.body, reply.active = body.body.strip(), body.active
    await session.commit()
    return quick_item(reply)


@router.delete('/quick-replies/{reply_id}', status_code=204)
async def delete_quick_reply(reply_id: int, who=Depends(manager), session=Depends(get_session)):
    reply = await session.get(QuickReply, reply_id)
    if reply is None:
        raise HTTPException(404, 'Mensaje no encontrado.')
    await session.delete(reply)
    await session.commit()


@router.get('/active-lives')
async def active_lives(who=Depends(reader), session=Depends(get_session)):
    """Operational card for agents and managers; no historic reports or contact identities."""
    from ..social_live.queries import list_lives
    result = await list_lives(session, limit=100, offset=0, status='live')
    return {'items': [{
        **{key: item[key] for key in ('id', 'status', 'account', 'tiktoker', 'started_at')},
        'metrics': {key: item['metrics'][key] for key in ('current_viewers', 'phones_captured')},
    } for item in result['items']]}


# ---- contacts table and summary -------------------------------------------------------------

def registry_visibility(who):
    me = who['user_id']
    if 'wa:read_all' in perms(who) or 'contacts:read_all' in perms(who):
        return None
    mine = ChatConversation.site_id.in_(sites.my_sites(me))
    if settings.auto_assignment:
        return or_(PhoneRegistry.advisor_id == me, mine)
    return or_(and_(PhoneRegistry.advisor_id.is_(None), ChatConversation.site_id.is_(None)),
               PhoneRegistry.advisor_id == me, mine)


@router.get('/contacts')
async def contacts(q: str = Query('', max_length=100),
                   stage: Literal['new', 'contacted', 'qualified', 'discarded'] | None = None,
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   who=Depends(reader), session=Depends(get_session)):
    """The patient base: LIVE contacts (with their WhatsApp conversation, if there is one) and
    WhatsApp-only numbers, most recent activity first."""
    me = who['user_id']
    needle = q.strip().lower()[:100]
    join = and_(ChatConversation.phone == PhoneRegistry.phone,
                ChatConversation.channel_id == wa.CHANNEL)
    first = select(PhoneRegistry, ChatConversation).outerjoin(ChatConversation, join)
    visible = registry_visibility(who)
    if visible is not None:
        first = first.where(visible)
    if stage:
        first = first.where(PhoneRegistry.status == stage)
    if needle:
        first = first.where(or_(
            PhoneRegistry.phone.contains(needle, autoescape=True),
            func.lower(func.coalesce(PhoneRegistry.first_username, '')).contains(needle, autoescape=True),
            func.lower(func.coalesce(ChatConversation.contact_name, '')).contains(needle, autoescape=True)))
    cap = offset + limit + 1
    registry_rows = (await session.execute(first.order_by(func.coalesce(
        ChatConversation.last_message_at, PhoneRegistry.first_captured_at).desc(),
        PhoneRegistry.id.desc()).limit(cap))).all()

    only = select(ChatConversation).where(
        ChatConversation.channel_id == wa.CHANNEL,
        ~exists(select(PhoneRegistry.id).where(PhoneRegistry.phone == ChatConversation.phone)))
    if 'wa:read_all' not in perms(who):
        only = only.where(sites.visible_to(me, ChatConversation.advisor_id))
    if stage:
        only = only.where(ChatConversation.stage == stage)
    if needle:
        only = only.where(or_(
            ChatConversation.phone.contains(needle, autoescape=True),
            func.lower(func.coalesce(ChatConversation.contact_name, '')).contains(needle, autoescape=True)))
    only_rows = (await session.scalars(only.order_by(ChatConversation.last_message_at.desc()
                                                     .nullslast()).limit(cap))).all()

    merged = [(aware(c.last_message_at) if c and c.last_message_at else aware(r.first_captured_at), r, c)
              for r, c in registry_rows]
    merged += [(aware(c.last_message_at) if c.last_message_at else aware(c.created_at), None, c)
               for c in only_rows]
    merged.sort(key=lambda row: row[0], reverse=True)
    page = merged[offset:offset + limit]

    conv_rows = [(c, r) for _, r, c in page if c is not None]
    conv_items = {i['id']: i for i in await build_items(session, conv_rows, who)}
    bare = [r for _, r, c in page if c is None]
    first_comments = await _first_comments(session, bare) if bare else {}
    bare_phones = [r.phone for r in bare]
    consent_map = {c.phone: c.status for c in (await session.scalars(select(ChatConsent).where(
        ChatConsent.phone.in_(bare_phones)))).all()} if bare_phones else {}
    opted_map = set((await session.scalars(select(OptOut.phone).where(
        OptOut.phone.in_(bare_phones)))).all()) if bare_phones else set()
    names = await names_of(session, {r.advisor_id for r in bare})
    items = []
    for _, registry, conversation in page:
        if conversation is not None:
            item = conv_items[conversation.id]
            comment = None
            if registry and not item['last']:
                comment = (await _first_comments(session, [registry])).get(registry.phone)
            items.append({**item, 'conversation_id': item['id'],
                          'message': item['last']['body'] if item['last']
                          else (comment.comment if comment else None)})
        else:
            comment = first_comments.get(registry.phone)
            items.append({
                'id': None, 'conversation_id': None, 'phone': registry.phone,
                'name': registry.first_username, 'registry_id': registry.id,
                'advisor_id': registry.advisor_id, 'advisor_name': names.get(registry.advisor_id),
                'is_mine': registry.advisor_id == me, 'stage': registry.status, 'result': None,
                'tags': [], 'archived': False, 'unread': 0, 'last_message_at': None, 'last': None,
                'consent': consent_map.get(registry.phone, 'unknown'),
                'opted_out': registry.phone in opted_map, 'origin': 'tiktok_live', 'lives': 1,
                'message': comment.comment if comment else None})
    return {'items': items, 'has_more': len(merged) > offset + limit}


@router.get('/summary')
async def summary(who=Depends(reader), session=Depends(get_session)):
    """The four numbers at the top of the CRM page."""
    visible = registry_visibility(who)
    total = select(func.count()).select_from(PhoneRegistry)
    if visible is not None:
        total = total.where(visible)
    contacts_total = await session.scalar(total) or 0
    opted = select(OptOut.phone)
    ready = select(func.count()).select_from(ChatConsent).where(
        ChatConsent.status == 'granted', ~ChatConsent.phone.in_(opted))
    in_chat = select(func.count()).select_from(ChatConversation).where(
        ChatConversation.channel_id == wa.CHANNEL, ChatConversation.archived.is_(False))
    if 'wa:read_all' not in perms(who):
        in_chat = in_chat.where(sites.visible_to(who['user_id'], ChatConversation.advisor_id))
    result = {'contacts': contacts_total, 'ready_for_whatsapp': await session.scalar(ready) or 0,
              'conversations': await session.scalar(in_chat) or 0, 'campaigns': None,
              'automations': None}
    if 'automation:read' in perms(who):
        result['campaigns'] = await session.scalar(select(func.count()).select_from(Broadcast)) or 0
        result['automations'] = await session.scalar(select(func.count()).select_from(Flow).where(
            Flow.enabled.is_(True))) or 0
    return result

