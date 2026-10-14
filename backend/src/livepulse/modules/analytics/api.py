"""Staff API and limited server-to-server bridge for Medical 360."""
import csv
import hmac
import io
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

import phonenumbers
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...shared.auth import get_current_user
from ...shared.config import settings
from ...shared.db import get_session
from ..broadcasts.models import RawEvent
from ..shifts.service import lock
from .access import register, require_role
from .classify import phones_in
from .models import (
    EventFact,
    Lead,
    LeadAlias,
    LeadAudit,
    LeadPhone,
    MonitorState,
    RoleAudit,
    UserRole,
)
from .processor import contact_for
from .reporting import attribution, lives

router = APIRouter(prefix='/v1')
marketing = require_role('marketing')
care = require_role('care')
admin = require_role()


@router.get('/capabilities')
async def capabilities(user=Depends(get_current_user), session=Depends(get_session)):
    return {'role': await register(session, user)}


@router.get('/analytics/lives')
async def report(account_id: str | None = None, limit: int = Query(20, ge=1, le=100),
                 offset: int = Query(0, ge=0), user=Depends(marketing), session=Depends(get_session)):
    return await lives(session, account_id, limit, offset)


@router.get('/analytics/lives/{broadcast_id}/attribution')
async def match(broadcast_id: int, user=Depends(marketing), session=Depends(get_session)):
    return await attribution(session, broadcast_id)


async def integration(x_medical360_token: str = Header(default='')):
    if not settings.medical360_token or not hmac.compare_digest(
            settings.medical360_token.encode(), x_medical360_token.encode()):
        raise HTTPException(401, 'Integración no autorizada')


@router.get('/integrations/medical360/lives', dependencies=[Depends(integration)])
async def integration_lives(account_id: str | None = None, limit: int = Query(20, ge=1, le=100),
                           offset: int = Query(0, ge=0), session=Depends(get_session)):
    return await lives(session, account_id, limit, offset)


@router.get('/monitor/status')
async def monitor_status(user=Depends(marketing), session=Depends(get_session)):
    now = datetime.now(timezone.utc)
    rows = (await session.scalars(select(MonitorState))).all()
    worker = next((r for r in rows if r.account_id == 'worker'), None)
    return {'worker_stale': not worker or now - worker.observed_at > timedelta(seconds=60),
            'accounts': [{'account_id': a, 'status': row.status if row else 'not_started',
                         'heartbeat': row.observed_at if row else None,
                         'stale': not row or now - row.observed_at > timedelta(seconds=150),
                         'error': row.last_error if row else None}
                        for a in settings.tiktok_accounts
                        for row in [next((r for r in rows if r.account_id == a), None)]],
            'pending_events': await session.scalar(select(func.count()).select_from(RawEvent)
                .outerjoin(EventFact, EventFact.event_id == RawEvent.event_id)
                .where(EventFact.event_id.is_(None))),
            'unlinked_events': await session.scalar(select(func.count()).select_from(RawEvent)
                .where(RawEvent.broadcast_id.is_(None)))}


@router.get('/staff/users')
async def users(user=Depends(admin), session=Depends(get_session)):
    return [{'id': r.user_id, 'role': 'admin' if r.user_id in settings.admin_user_ids else r.role}
            for r in (await session.scalars(select(UserRole).order_by(UserRole.user_id))).all()]


class RoleBody(BaseModel):
    role: Literal['tiktoker', 'marketing', 'care', 'admin']


@router.put('/staff/users/{user_id}/role')
async def set_role(user_id: str, body: RoleBody, user=Depends(admin), session=Depends(get_session)):
    if user_id in settings.admin_user_ids or user_id == user['id']:
        raise HTTPException(409, 'No puedes cambiar tu propio rol ni el administrador inicial.')
    row = await session.get(UserRole, user_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'La persona debe entrar primero a LivePulse.')
    row.role = body.role
    session.add(RoleAudit(id=str(uuid4()), actor=user['id'], user_id=user_id, role=body.role))
    await session.commit()
    return {'id': user_id, 'role': row.role}


@router.get('/contacts')
async def contacts(offset: int = Query(0, ge=0), user=Depends(care), session=Depends(get_session)):
    rows = (await session.scalars(select(Lead).order_by(Lead.created_at.desc(), Lead.id)
                                  .offset(offset).limit(51))).all()
    items = []
    for row in rows[:50]:
        aliases = (await session.scalars(select(LeadAlias).where(LeadAlias.lead_id == row.id))).all()
        phones = (await session.scalars(select(LeadPhone.phone).where(LeadPhone.lead_id == row.id))).all()
        items.append({'id': row.id, 'status': row.status, 'review_needed': row.review_needed,
                      'users': [a.username or a.user_key for a in aliases], 'phones': phones})
    return {'items': items, 'next_offset': offset + 50 if len(rows) > 50 else None}


class ContactBody(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    username: str | None = Field(default=None, max_length=100)


@router.post('/contacts/manual')
async def manual(body: ContactBody, user=Depends(care), session=Depends(get_session)):
    phones = phones_in(body.text)
    if not phones:
        raise HTTPException(422, 'No se encontraron teléfonos válidos; revisa la transcripción.')
    # Manual handles have a separate namespace from provider numeric IDs.
    key = 'handle:' + body.username.strip().lower().lstrip('@') if body.username else None
    lead_id = await contact_for(session, key, body.username, phones)
    session.add(LeadAudit(id=str(uuid4()), lead_id=lead_id, actor=user['id'], action='manual'))
    await session.commit()
    return {'id': lead_id, 'phones': phones}


class StatusBody(BaseModel):
    status: Literal['new', 'ready', 'contacted', 'scheduled', 'closed', 'invalid']
    expected_status: str
    note: str = Field(default='', max_length=500)


@router.patch('/contacts/{lead_id}')
async def update_contact(lead_id: str, body: StatusBody, user=Depends(care), session=Depends(get_session)):
    row = await session.get(Lead, lead_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Contacto no encontrado')
    if row.status != body.expected_status:
        raise HTTPException(409, 'Otra persona actualizó este contacto. Recarga la lista.')
    session.add(LeadAudit(id=str(uuid4()), lead_id=lead_id, actor=user['id'], action='status',
                         previous=row.status, value=body.status, note=body.note))
    row.status = body.status
    await session.commit()
    return {'id': lead_id, 'status': row.status}


def csv_safe(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


@router.post('/contacts/export/leadsales')
async def export_leads(user=Depends(care), session=Depends(get_session)):
    await lock(session, 'lead-export')
    rows = (await session.scalars(select(Lead).where(Lead.status == 'ready',
        Lead.review_needed.is_(False)).order_by(Lead.created_at).limit(500).with_for_update())).all()
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Area code', 'Phone', 'Name', 'Value', 'Email', 'Tags', 'Company', 'Assignee'])
    for row in rows:
        phones = (await session.scalars(select(LeadPhone.phone).where(LeadPhone.lead_id == row.id)
                                       .order_by(LeadPhone.phone))).all()
        if not phones:
            continue
        alias = await session.scalar(select(LeadAlias).where(LeadAlias.lead_id == row.id)
                                     .order_by(LeadAlias.user_key).limit(1))
        for phone in phones:
            parsed = phonenumbers.parse(phone, None)
            writer.writerow([parsed.country_code, parsed.national_number,
                             csv_safe(alias.username or alias.user_key) if alias else row.id,
                             '', '', 'TikTok,LivePulse', '', ''])
    # Download does not prove import or delivery: contacts remain ready for a safe retry.
    return {'filename': 'livepulse-leadsales.csv', 'csv': output.getvalue(),
            'note': 'Importa el archivo en Leadsales y registra el seguimiento en LivePulse.'}


class ReviewBody(BaseModel):
    note: str = Field(min_length=10, max_length=500)


@router.post('/contacts/{lead_id}/review')
async def resolve_review(lead_id: str, body: ReviewBody, user=Depends(admin), session=Depends(get_session)):
    row = await session.get(Lead, lead_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Contacto no encontrado')
    row.review_needed = False
    session.add(LeadAudit(id=str(uuid4()), lead_id=lead_id, actor=user['id'],
                         action='review', note=body.note))
    await session.commit()
    return {'id': lead_id, 'review_needed': False}
