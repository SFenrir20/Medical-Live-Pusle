"""What the automatic rules did, how to undo it, and a tester for the appointment message."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...shared.db import get_session
from ..chat.service import utcnow
from ..social_live.security import require_scope
from ..whatsapp import api as wa_api
from . import autopipeline, sites
from .api import iso, perms, reader
from .appointments import parse_appointment, starts_at
from .models import AutoLog

router = APIRouter(prefix='/api/crm/automation', tags=['crm-automation'])
tester = require_scope('crm:manage')


@router.get('/log')
async def log_of(conversation_id: int = Query(..., ge=1), who=Depends(reader),
                 session=Depends(get_session)):
    """The automatic movements of one conversation (the people who may see it)."""
    await wa_api.access(session, conversation_id, who)
    rows = (await session.scalars(select(AutoLog).where(
        AutoLog.conversation_id == conversation_id).order_by(AutoLog.id.desc()).limit(20))).all()
    return {'items': [{'id': r.id, 'kind': r.kind, 'summary': r.summary, 'at': iso(r.created_at),
                       'undone': r.undone_at is not None} for r in rows],
            'can_undo': 'contacts:assign_any' in perms(who)}


@router.post('/{log_id}/undo')
async def undo(log_id: int, who=Depends(reader), session=Depends(get_session)):
    """Put the conversation back as it was before the rule ran. Supervisors."""
    if 'contacts:assign_any' not in perms(who):
        raise HTTPException(403, 'Solo un supervisor puede deshacer un movimiento automático.')
    row = await session.get(AutoLog, log_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Movimiento no encontrado.')
    if row.undone_at is not None:
        raise HTTPException(409, 'Ese movimiento ya se deshizo.')
    newer = await session.scalar(select(AutoLog.id).where(
        AutoLog.conversation_id == row.conversation_id, AutoLog.id > row.id,
        AutoLog.undone_at.is_(None)).limit(1))
    if newer is not None:
        raise HTTPException(409, 'Hay un movimiento automático más reciente: deshazlo primero.')
    await autopipeline.undo(session, row, who['user_id'])
    await session.commit()
    return {'id': row.id, 'undone_at': iso(row.undone_at)}


class Sample(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post('/preview')
async def preview(body: Sample, who=Depends(tester), session=Depends(get_session)):
    """What the rule would understand from a message, without changing anything."""
    appointment = parse_appointment(body.text, utcnow().astimezone(autopipeline.LIMA).date())
    if appointment is None:
        return {'is_appointment': False}
    site = await sites.match_site(session, appointment.site_text)
    when = starts_at(appointment, autopipeline.LIMA)
    return {'is_appointment': True, 'patient': appointment.patient,
            'site': site.name if site else None, 'site_text': appointment.site_text,
            'date': appointment.day.isoformat() if appointment.day else None,
            'hour': appointment.start.strftime('%H:%M') if appointment.start else None,
            'starts_at': when.isoformat() if when else None}
