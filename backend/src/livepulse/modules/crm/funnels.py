"""Funnels (embudos): the built-in one, the templates, and the log of moves between stages.

The built-in funnel ("Contactos") mirrors the contact's own status, so there is still a single
truth for the stage of a LIVE contact. Other funnels are independent: a conversation is in them
only after someone adds it, and may be in several at once."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..chat.service import utcnow
from .models import Pipeline, PipelineEvent, PipelineStage

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
                               actor: str) -> None:
    """A change of the contact's own stage (from the inbox or a board) is a move in the built-in funnel."""
    if before == after:
        return
    pipeline = await ensure_default(session)
    by_legacy = {s.legacy_stage: s.id for s in await stages_of(session, pipeline.id)}
    if after in by_legacy:
        await record_move(session, pipeline.id, conversation_id, by_legacy.get(before),
                          by_legacy[after], actor)
