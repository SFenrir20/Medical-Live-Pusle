"""The automatic funnel: nobody has to click, tag or move anything.

When the appointments centre confirms an appointment to a patient (the message with Paciente,
Fecha, Hora and Sede, see appointments.py) and that message was really sent, the patient:
  1. reaches "Cita agendada" in the contact funnel, where the centre's work ends;
  2. gets the tags of the branch and of the appointment (and "Del LIVE" if it came from one);
  3. enters the funnel of that branch, in its first stage, and from then on only that branch sees it;
  4. is handed to the advisor of the branch whose shift covers the appointment hour (sites.py), or
     waits, free, in the branch pool when nobody covers it.
Every run is written to crm_auto_log with what it needs to be undone, and is idempotent per
message: a message seen twice, or re-sent, does not move anyone twice."""
import logging
from datetime import timedelta, timezone

from sqlalchemy import select

from ..analytics.models import UserRole
from ..chat import hooks
from ..chat.models import ChatConversation
from ..chat.service import utcnow
from ..social_live import contacts as workflow
from ..social_live.models import PhoneRegistry
from ..social_live.service import audit
from . import funnels, sites
from .appointments import parse_appointment, starts_at
from .models import AutoLog, PipelineCard

log = logging.getLogger(__name__)
LIMA = timezone(timedelta(hours=-5))
SYSTEM = 'system:auto'
SENT = ('sent', 'delivered', 'read')
QUALIFIED = 'qualified'


def owner_of(conversation, registry):
    return registry.advisor_id if registry else conversation.advisor_id


def stage_of(conversation, registry) -> str:
    return registry.status if registry else conversation.stage


async def registry_of(session, conversation):
    return await session.scalar(select(PhoneRegistry).where(
        PhoneRegistry.phone == conversation.phone).with_for_update())


async def set_stage(session, conversation, registry, stage: str) -> None:
    """The contact's own stage (a LIVE contact keeps it on the contact, with its audit)."""
    before = stage_of(conversation, registry)
    if before == stage:
        return
    if registry:
        values = {'status': stage}
        if stage in workflow.CONTACTED and registry.contacted_at is None:
            values['contacted_at'] = utcnow()
        await workflow._apply(session, registry, values)
        await audit(session, registry.id, SYSTEM, 'status', before, stage)
    else:
        conversation.stage = stage
    await funnels.record_contact_stage(session, conversation.id, before, stage, SYSTEM)


async def set_owner(session, conversation, registry, advisor_id) -> None:
    current = owner_of(conversation, registry)
    if current == advisor_id:
        return
    if registry:
        if advisor_id:
            await workflow.assign(session, registry.id, SYSTEM, advisor_id, manager=True)
        else:
            await workflow.release(session, registry.id, SYSTEM, manager=True)
    else:
        conversation.advisor_id = advisor_id


async def name_of(session, user_id) -> str:
    row = await session.get(UserRole, user_id) if user_id else None
    return (row.display_name if row and row.display_name else user_id) or ''


async def on_outbound(session, conversation, message) -> None:
    if message.direction != 'out' or message.status not in SENT:
        return
    today = (message.sent_at or message.created_at or utcnow()).astimezone(LIMA).date()
    appointment = parse_appointment(message.body, today)
    if appointment is None:
        return
    if await session.scalar(select(AutoLog.id).where(AutoLog.kind == 'appointment',
                                                      AutoLog.message_id == message.id)):
        return
    registry = await registry_of(session, conversation)
    site = await sites.match_site(session, appointment.site_text)
    when = starts_at(appointment, LIMA)

    before = {'advisor_id': owner_of(conversation, registry), 'stage': stage_of(conversation, registry),
              'tags': list(conversation.tags or []), 'site_id': conversation.site_id,
              'appointment_at': conversation.appointment_at.isoformat() if conversation.appointment_at else None,
              'appointment_label': conversation.appointment_label, 'cards': []}
    steps = []

    await set_stage(session, conversation, registry, QUALIFIED)
    steps.append('cita agendada')
    tags = set(conversation.tags or []) | {'Cita agendada'}
    if registry:
        tags.add('Del LIVE')
    conversation.appointment_at = when.astimezone(timezone.utc) if when else None
    conversation.appointment_label = appointment.label

    if site is None:
        conversation.tags = sorted(tags)
        summary = (f'Cita agendada ({appointment.label}). La sede «{appointment.site_text}» no coincide '
                   'con ninguna sede registrada: no se asignó asesor. Revisa las sedes en Ajustes.')
    else:
        tags.add(site.name)
        conversation.tags = sorted(tags)
        previous_site = conversation.site_id
        conversation.site_id = site.id
        if previous_site and previous_site != site.id:
            old = (await session.scalars(select(PipelineCard).join(
                funnels.Pipeline, funnels.Pipeline.id == PipelineCard.pipeline_id).where(
                funnels.Pipeline.site_id == previous_site,
                PipelineCard.conversation_id == conversation.id))).all()
            for card in old:
                before['cards'].append({'pipeline_id': card.pipeline_id, 'stage_id': card.stage_id,
                                        'value_cents': int(card.value_cents), 'removed': True})
                await session.delete(card)
        pipeline = await sites.site_funnel(session, site)
        first = (await funnels.stages_of(session, pipeline.id))[0]
        card = await session.scalar(select(PipelineCard).where(
            PipelineCard.pipeline_id == pipeline.id, PipelineCard.conversation_id == conversation.id))
        if card is None:
            session.add(PipelineCard(pipeline_id=pipeline.id, conversation_id=conversation.id,
                                     stage_id=first.id, entered_at=utcnow(), updated_by=SYSTEM))
            await funnels.record_move(session, pipeline.id, conversation.id, None, first.id, SYSTEM)
            before['cards'].append({'pipeline_id': pipeline.id, 'created': True})
        steps.append(f'embudo de {site.name}')

        keep = previous_site == site.id and before['advisor_id'] and \
            before['advisor_id'] in await site_advisors(session, site.id)
        if keep:
            advisor = before['advisor_id']
            steps.append('se mantiene su asesor')
        else:
            advisor = await sites.choose_advisor(session, site.id, appointment.start)
            await set_owner(session, conversation, registry, advisor)
            steps.append(f'asignada a {await name_of(session, advisor)}' if advisor
                         else 'sin asesor que cubra ese horario: queda libre en la sede')
        summary = f'Cita agendada en {site.name} ({appointment.label}): ' + ', '.join(steps) + '.'

    session.add(AutoLog(conversation_id=conversation.id, message_id=message.id, kind='appointment',
                        summary=summary[:300], before=before, created_at=utcnow()))


async def site_advisors(session, site_id: int) -> set[str]:
    return set((await session.scalars(select(sites.Staff.user_id).where(
        sites.Staff.site_id == site_id, sites.Staff.active.is_(True)))).all())


async def undo(session, log_row: AutoLog, actor: str) -> None:
    """Put the conversation back as it was before the rule ran."""
    conversation = await session.get(ChatConversation, log_row.conversation_id)
    registry = await registry_of(session, conversation)
    before = log_row.before or {}
    await set_stage(session, conversation, registry, before.get('stage', 'new'))
    await set_owner(session, conversation, registry, before.get('advisor_id'))
    conversation.tags = before.get('tags', [])
    conversation.site_id = before.get('site_id')
    conversation.appointment_label = before.get('appointment_label')
    stamp = before.get('appointment_at')
    conversation.appointment_at = None
    if stamp:
        from datetime import datetime
        conversation.appointment_at = datetime.fromisoformat(stamp)
    for item in before.get('cards', []):
        card = await session.scalar(select(PipelineCard).where(
            PipelineCard.pipeline_id == item['pipeline_id'],
            PipelineCard.conversation_id == conversation.id))
        if item.get('created') and card is not None:
            await session.delete(card)
        elif item.get('removed') and card is None:
            session.add(PipelineCard(pipeline_id=item['pipeline_id'], conversation_id=conversation.id,
                                     stage_id=item['stage_id'], value_cents=item.get('value_cents', 0),
                                     entered_at=utcnow(), updated_by=actor))
    log_row.undone_at, log_row.undone_by = utcnow(), actor


hooks.register_outbound(on_outbound)
