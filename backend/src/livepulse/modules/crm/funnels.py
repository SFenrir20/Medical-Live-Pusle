"""Funnels (embudos): the built-in one, the templates, and the log of moves between stages.

The built-in funnel ("Contactos") mirrors the contact's own status, so there is still a single
truth for the stage of a LIVE contact. Other funnels are independent: a conversation is in them
only after someone adds it, and may be in several at once."""
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError

from ..chat.service import utcnow
from .models import Pipeline, PipelineCard, PipelineEvent, PipelineStage

DEFAULT_KEY = 'contacts'
# (name, color, contact status it stands for)
DEFAULT_STAGES = [
    ('Nuevo', '#0ea5e9', 'new'),
    ('Contactado', '#f59e0b', 'contacted'),
    ('Cita agendada', '#10b981', 'qualified'),
    ('Descartado', '#94a3b8', 'discarded'),
]
COLORS = ('#0f92ac', '#14b8a6', '#22c55e', '#f59e0b', '#7c3aed', '#ec4899', '#0ea5e9', '#94a3b8')
MAX_PIPELINES = 15
MAX_STAGES = 12

TEMPLATES: dict[str, dict] = {
    'tiktok_live': {
        'name': 'TikTok LIVE a cita',
        'stages': [('Contactos captados', 'Teléfono detectado durante un LIVE.'),
                   ('Primer contacto', 'Se envió la bienvenida.'),
                   ('Paciente calificado', 'Interés y procedimiento identificados.'),
                   ('Evaluación agendada', 'Tiene fecha de evaluación.'),
                   ('Paciente confirmado', 'Confirmó su asistencia.')]},
    'whatsapp': {
        'name': 'WhatsApp a paciente',
        'stages': [('Consulta nueva', 'Escribió por WhatsApp.'),
                   ('En conversación', 'Se le está atendiendo.'),
                   ('Cotización enviada', 'Recibió precio o presupuesto.'),
                   ('Cita agendada', 'Tiene fecha de cita.'),
                   ('Operado', 'Cerró el tratamiento.')]},
    'reactivation': {
        'name': 'Reactivación',
        'stages': [('Sin respuesta', 'No contestó o no agendó.'),
                   ('Reactivado', 'Volvió a responder.'),
                   ('Cita agendada', 'Agendó después de reactivar.')]},
    'blank': {
        'name': 'Nuevo embudo',
        'stages': [('Nuevo', None), ('En proceso', None), ('Cerrado', None)]},
}


async def ensure_default(session) -> Pipeline:
    """The built-in funnel, created on first use (safe if two requests race)."""
    found = await session.scalar(select(Pipeline).where(Pipeline.key == DEFAULT_KEY))
    if found is not None:
        return found
    try:
        async with session.begin_nested():
            pipeline = Pipeline(key=DEFAULT_KEY, name='Contactos', position=0, created_at=utcnow())
            session.add(pipeline)
            await session.flush()
            for index, (name, color, legacy) in enumerate(DEFAULT_STAGES):
                session.add(PipelineStage(pipeline_id=pipeline.id, name=name, color=color,
                                          position=index, legacy_stage=legacy))
            await session.flush()
        return pipeline
    except IntegrityError:
        return await session.scalar(select(Pipeline).where(Pipeline.key == DEFAULT_KEY))


async def stages_of(session, pipeline_id: int) -> list[PipelineStage]:
    return list((await session.scalars(select(PipelineStage).where(
        PipelineStage.pipeline_id == pipeline_id).order_by(PipelineStage.position,
                                                           PipelineStage.id))).all())


async def record_move(session, pipeline_id: int, conversation_id: int, from_stage_id, to_stage_id,
                      actor: str) -> None:
    session.add(PipelineEvent(pipeline_id=pipeline_id, conversation_id=conversation_id,
                              from_stage_id=from_stage_id, to_stage_id=to_stage_id,
                              actor_id=actor, at=utcnow()))


async def record_contact_stage(session, conversation_id: int, before: str, after: str,
                               actor: str) -> list[int]:
    """A change of the contact's own stage (from the inbox or a board) is a move in the built-in funnel."""
    created = await enter_qualified(session, conversation_id) if after == 'qualified' else []
    if before == after:
        return created
    pipeline = await ensure_default(session)
    by_legacy = {s.legacy_stage: s.id for s in await stages_of(session, pipeline.id)}
    if after in by_legacy:
        await record_move(session, pipeline.id, conversation_id, by_legacy.get(before),
                          by_legacy[after], actor)
    return created


async def enter_qualified(session, conversation_id: int, pipeline=None) -> list[int]:
    """Add once, without resetting an existing card's stage, value, owner or conversation.

    The unique card index and savepoint make concurrent/repeated qualification safe.
    Branch funnels retain their separate appointment/site routing.
    """
    targets = [pipeline] if pipeline is not None else list((await session.scalars(
        select(Pipeline).where(Pipeline.auto_qualified.is_(True), Pipeline.archived.is_(False),
                               Pipeline.site_id.is_(None)))).all())
    created = []
    for target in targets:
        if target.key == DEFAULT_KEY or target.archived or not target.auto_qualified or target.site_id:
            continue
        stages = await stages_of(session, target.id)
        if not stages:
            continue
        existing = await session.scalar(select(PipelineCard.id).where(
            PipelineCard.pipeline_id == target.id, PipelineCard.conversation_id == conversation_id))
        if existing is not None:
            continue
        try:
            async with session.begin_nested():
                session.add(PipelineCard(pipeline_id=target.id, conversation_id=conversation_id,
                                         stage_id=stages[0].id, entered_at=utcnow(),
                                         updated_by='system:qualified'))
                await session.flush()
                await record_move(session, target.id, conversation_id, None, stages[0].id,
                                  'system:qualified')
            created.append(target.id)
        except IntegrityError:
            # Only swallow a race on the unique membership, not an unrelated constraint failure.
            if await session.scalar(select(PipelineCard.id).where(
                    PipelineCard.pipeline_id == target.id,
                    PipelineCard.conversation_id == conversation_id)) is None:
                raise
    return created


async def backfill_qualified(session, pipeline) -> None:
    from ..chat.models import ChatConversation
    from ..social_live.models import PhoneRegistry

    status = case((PhoneRegistry.id.is_not(None), PhoneRegistry.status), else_=ChatConversation.stage)
    ids = (await session.scalars(select(ChatConversation.id).outerjoin(
        PhoneRegistry, PhoneRegistry.phone == ChatConversation.phone).where(status == 'qualified'))).all()
    for conversation_id in ids:
        await enter_qualified(session, conversation_id, pipeline)
