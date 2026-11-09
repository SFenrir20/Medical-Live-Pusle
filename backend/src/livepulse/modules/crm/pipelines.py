"""Funnels (embudos) as a board: columns are stages, cards are conversations.

Who can do what (same rules as the rest of the CRM):
  * everyone with `wa:read` sees the cards of the conversations the mirror lets them see;
  * moving a card, or setting its value, needs the conversation to be yours (or the supervisor's
    `contacts:assign_any`): a free one must be taken first;
  * creating, renaming and archiving funnels and editing their stages is `crm:manage`;
  * the built-in funnel "Contactos" mirrors the contact's status: it can be used but not edited."""
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import and_, case, func, select, union

from ...shared.db import get_session
from ..chat.models import ChatConversation
from ..chat.service import utcnow
from ..social_live.models import PhoneRegistry
from . import funnels
from .api import (
    build_items,
    in_scope,
    manager,
    matching,
    reader,
    set_stage,
    stage_of,
    visible_conversations,
    writable,
)
from .models import Pipeline, PipelineCard, PipelineEvent, PipelineStage

router = APIRouter(prefix='/api/crm/pipelines', tags=['crm-pipelines'])
PAGE = 30
COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
MAX_VALUE = 10 ** 11   # cents


# ---- helpers ---------------------------------------------------------------------------------

def stage_item(stage: PipelineStage) -> dict:
    return {'id': stage.id, 'name': stage.name, 'color': stage.color,
            'description': stage.description, 'position': stage.position,
            'legacy_stage': stage.legacy_stage}


def pipeline_item(pipeline: Pipeline) -> dict:
    return {'id': pipeline.id, 'name': pipeline.name, 'default': pipeline.key == funnels.DEFAULT_KEY}


async def load(session, pipeline_id: int, *, active: bool = True) -> Pipeline:
    await funnels.ensure_default(session)
    pipeline = await session.get(Pipeline, pipeline_id)
    if pipeline is None or (active and pipeline.archived):
        raise HTTPException(404, 'Embudo no encontrado.')
    return pipeline


def is_default(pipeline: Pipeline) -> bool:
    return pipeline.key == funnels.DEFAULT_KEY


def stage_key(pipeline: Pipeline):
    """The column of a conversation: the contact's own status in the built-in funnel, the card's
    stage in the others."""
    if is_default(pipeline):
        return case((PhoneRegistry.id.is_not(None), PhoneRegistry.status), else_=ChatConversation.stage)
    return PipelineCard.stage_id


def stage_value(pipeline: Pipeline, stage: PipelineStage):
    return stage.legacy_stage if is_default(pipeline) else stage.id


def cards_select(who, pipeline: Pipeline, q: str, mine: bool):
    """(conversation, contact, value, entered_at) of the cards this person may see."""
    base = in_scope(visible_conversations(who), 'mine' if mine else 'all', who['user_id'])
    base = matching(base, q)
    base = base.add_columns(PipelineCard.value_cents, PipelineCard.entered_at)
    on = and_(PipelineCard.pipeline_id == pipeline.id, PipelineCard.conversation_id == ChatConversation.id)
    return base.outerjoin(PipelineCard, on) if is_default(pipeline) else base.join(PipelineCard, on)


def ordered(query):
    return query.order_by(ChatConversation.last_message_at.desc().nullslast(), ChatConversation.id.desc())


async def card_items(session, rows, who) -> list[dict]:
    items = await build_items(session, [(c, r) for c, r, *_ in rows], who)
    for item, (_, _, value, entered) in zip(items, rows, strict=True):
        item['value_cents'] = int(value or 0)
        item['entered_at'] = entered.isoformat() if entered is not None else None
    return items


# ---- funnels ---------------------------------------------------------------------------------

@router.get('')
async def list_pipelines(who=Depends(reader), session=Depends(get_session)):
    await funnels.ensure_default(session)
    rows = (await session.scalars(select(Pipeline).where(Pipeline.archived.is_(False)).order_by(
        Pipeline.position, Pipeline.id))).all()
    await session.commit()
    return {'items': [pipeline_item(p) for p in rows]}


@router.get('/templates')
async def templates(who=Depends(reader)):
    return {'items': [{'key': key, 'name': value['name'], 'stages': [s[0] for s in value['stages']]}
                      for key, value in funnels.TEMPLATES.items()]}


class PipelineIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    template: str = 'blank'


async def detail(session, pipeline: Pipeline) -> dict:
    return {**pipeline_item(pipeline),
            'stages': [stage_item(s) for s in await funnels.stages_of(session, pipeline.id)]}


@router.post('', status_code=201)
async def create_pipeline(body: PipelineIn, who=Depends(manager), session=Depends(get_session)):
    template = funnels.TEMPLATES.get(body.template)
    if template is None:
        raise HTTPException(422, 'Plantilla no válida.')
    await funnels.ensure_default(session)
    active = await session.scalar(select(func.count()).select_from(Pipeline).where(
        Pipeline.archived.is_(False))) or 0
    if active >= funnels.MAX_PIPELINES:
        raise HTTPException(409, f'Puedes tener hasta {funnels.MAX_PIPELINES} embudos activos.')
    pipeline = Pipeline(name=body.name, position=active, created_by=who['user_id'], created_at=utcnow())
    session.add(pipeline)
    await session.flush()
    for index, (name, description) in enumerate(template['stages']):
        session.add(PipelineStage(pipeline_id=pipeline.id, name=name, description=description,
                                  color=funnels.COLORS[index % len(funnels.COLORS)], position=index))
    await session.commit()
    return await detail(session, pipeline)


class PipelinePatch(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None = None
    archived: bool | None = None


@router.patch('/{pipeline_id}')
async def patch_pipeline(pipeline_id: int, body: PipelinePatch, who=Depends(manager),
                         session=Depends(get_session)):
    pipeline = await load(session, pipeline_id, active=False)
    if is_default(pipeline):
        raise HTTPException(409, 'El embudo «Contactos» refleja el estado del contacto y no se edita.')
    if body.name is not None:
        pipeline.name = body.name
    if body.archived is not None:
        pipeline.archived = body.archived
    await session.commit()
    return await detail(session, pipeline)


class StageIn(BaseModel):
    id: int | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    color: str = '#0f92ac'
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class StagesIn(BaseModel):
    stages: list[StageIn] = Field(min_length=1, max_length=funnels.MAX_STAGES)


@router.put('/{pipeline_id}/stages')
async def save_stages(pipeline_id: int, body: StagesIn, who=Depends(manager),
                      session=Depends(get_session)):
    """The whole list of stages, in order (what the builder saves). A stage that still holds
    conversations cannot be removed: move them first."""
    pipeline = await load(session, pipeline_id)
    if is_default(pipeline):
        raise HTTPException(409, 'El embudo «Contactos» refleja el estado del contacto y no se edita.')
    if any(not COLOR.match(s.color) for s in body.stages):
        raise HTTPException(422, 'Color no válido.')
    current = {s.id: s for s in await funnels.stages_of(session, pipeline.id)}
    sent = [s.id for s in body.stages if s.id is not None]
    if len(sent) != len(set(sent)) or any(i not in current for i in sent):
        raise HTTPException(422, 'Etapa no válida.')
    removed = [s for i, s in current.items() if i not in sent]
    for stage in removed:
        holding = await session.scalar(select(func.count()).select_from(PipelineCard).where(
            PipelineCard.stage_id == stage.id)) or 0
        if holding:
            raise HTTPException(409, f'«{stage.name}» tiene {holding} contactos. Muévelos a otra '
                                     'etapa antes de eliminarla.')
    for index, item in enumerate(body.stages):
        row = current.get(item.id) if item.id is not None else None
        if row is None:
            row = PipelineStage(pipeline_id=pipeline.id)
            session.add(row)
        row.name, row.color, row.description, row.position = (
            item.name, item.color.lower(), item.description or None, index)
    for stage in removed:
        await session.delete(stage)
    await session.commit()
    return await detail(session, pipeline)


# ---- board -----------------------------------------------------------------------------------

@router.get('/{pipeline_id}/board')
async def board(pipeline_id: int, q: str = Query('', max_length=100), mine: bool = False,
                who=Depends(reader), session=Depends(get_session)):
    pipeline = await load(session, pipeline_id)
    stages = await funnels.stages_of(session, pipeline.id)
    key = stage_key(pipeline)
    base = cards_select(who, pipeline, q, mine)
    totals = {k: (n, int(v or 0)) for k, n, v in (await session.execute(
        base.with_only_columns(key, func.count(), func.coalesce(func.sum(PipelineCard.value_cents), 0),
                               maintain_column_froms=True).group_by(key))).all()}
    columns = []
    for stage in stages:
        wanted = stage_value(pipeline, stage)
        rows = (await session.execute(ordered(base.where(key == wanted)).limit(PAGE + 1))).all()
        count, value = totals.get(wanted, (0, 0))
        columns.append({**stage_item(stage), 'count': count, 'value_cents': value,
                        'cards': await card_items(session, rows[:PAGE], who),
                        'has_more': len(rows) > PAGE})
    await session.commit()   # the built-in funnel may have just been created
    return {'pipeline': pipeline_item(pipeline), 'stages': columns,
            'total': sum(c['count'] for c in columns),
            'value_cents': sum(c['value_cents'] for c in columns)}


@router.get('/{pipeline_id}/stages/{stage_id}/cards')
async def more_cards(pipeline_id: int, stage_id: int, offset: int = Query(0, ge=0),
                     q: str = Query('', max_length=100), mine: bool = False,
                     who=Depends(reader), session=Depends(get_session)):
    pipeline = await load(session, pipeline_id)
    stage = await session.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != pipeline.id:
        raise HTTPException(404, 'Etapa no encontrada.')
    rows = (await session.execute(ordered(cards_select(who, pipeline, q, mine).where(
        stage_key(pipeline) == stage_value(pipeline, stage))).offset(offset).limit(PAGE + 1))).all()
    return {'cards': await card_items(session, rows[:PAGE], who), 'has_more': len(rows) > PAGE}


class CardIn(BaseModel):
    stage_id: int | None = None
    value_cents: int | None = Field(default=None, ge=0, le=MAX_VALUE)


@router.put('/{pipeline_id}/cards/{conversation_id}')
async def put_card(pipeline_id: int, conversation_id: int, body: CardIn, who=Depends(reader),
                   session=Depends(get_session)):
    """Add a conversation to a funnel, move it to another stage, or set its value."""
    pipeline = await load(session, pipeline_id)
    conversation, registry = await writable(session, conversation_id, who)
    stages = {s.id: s for s in await funnels.stages_of(session, pipeline.id)}
    target = None
    if body.stage_id is not None:
        target = stages.get(body.stage_id)
        if target is None:
            raise HTTPException(422, 'Esa etapa no es de este embudo.')
    card = await session.scalar(select(PipelineCard).where(
        PipelineCard.pipeline_id == pipeline.id,
        PipelineCard.conversation_id == conversation.id).with_for_update())
    now = utcnow()
    if is_default(pipeline):
        if target is not None:
            await set_stage(session, conversation, registry, who, target.legacy_stage)
        if body.value_cents is not None:
            if card is None:
                card = PipelineCard(pipeline_id=pipeline.id, conversation_id=conversation.id,
                                    entered_at=now)
                session.add(card)
            card.value_cents, card.updated_by = body.value_cents, who['user_id']
    else:
        if card is None:
            if target is None:
                raise HTTPException(422, 'Elige la etapa donde entra.')
            card = PipelineCard(pipeline_id=pipeline.id, conversation_id=conversation.id,
                                stage_id=target.id, entered_at=now, value_cents=body.value_cents or 0)
            session.add(card)
            await funnels.record_move(session, pipeline.id, conversation.id, None, target.id,
                                      who['user_id'])
        else:
            if target is not None and target.id != card.stage_id:
                await funnels.record_move(session, pipeline.id, conversation.id, card.stage_id,
                                          target.id, who['user_id'])
                card.stage_id, card.entered_at = target.id, now
            if body.value_cents is not None:
                card.value_cents = body.value_cents
        card.updated_by = who['user_id']
    await session.commit()
    stage_id = (target.id if target else None) if is_default(pipeline) else card.stage_id
    if is_default(pipeline):
        mapping = {s.legacy_stage: s.id for s in stages.values()}
        stage_id = mapping.get(stage_of(conversation, registry))
    return {'conversation_id': conversation.id, 'stage_id': stage_id,
            'value_cents': int(card.value_cents) if card is not None else 0}


@router.delete('/{pipeline_id}/cards/{conversation_id}', status_code=204)
async def remove_card(pipeline_id: int, conversation_id: int, who=Depends(reader),
                      session=Depends(get_session)):
    pipeline = await load(session, pipeline_id)
    if is_default(pipeline):
        raise HTTPException(409, 'En «Contactos» cada conversación cambia de etapa, no se quita.')
    await writable(session, conversation_id, who)
    card = await session.scalar(select(PipelineCard).where(
        PipelineCard.pipeline_id == pipeline.id, PipelineCard.conversation_id == conversation_id))
    if card is not None:
        await session.delete(card)
        await session.commit()


@router.get('/{pipeline_id}/metrics')
async def metrics(pipeline_id: int, who=Depends(reader), session=Depends(get_session)):
    """Per stage: how many are in it now and how many ever entered it (from the log of moves,
    which starts when funnels were introduced)."""
    pipeline = await load(session, pipeline_id)
    key = stage_key(pipeline)
    base = cards_select(who, pipeline, '', False)
    visible = in_scope(visible_conversations(who), 'all', who['user_id']).with_only_columns(
        ChatConversation.id, maintain_column_froms=True)
    out = []
    for stage in await funnels.stages_of(session, pipeline.id):
        current = base.where(key == stage_value(pipeline, stage)).with_only_columns(
            ChatConversation.id, maintain_column_froms=True)
        passed = select(PipelineEvent.conversation_id).where(
            PipelineEvent.pipeline_id == pipeline.id, PipelineEvent.to_stage_id == stage.id,
            PipelineEvent.conversation_id.in_(visible))
        now_count = await session.scalar(select(func.count()).select_from(current.subquery())) or 0
        entered = await session.scalar(select(func.count()).select_from(
            union(current, passed).subquery())) or 0
        out.append({'stage_id': stage.id, 'current': now_count, 'entered': entered})
    await session.commit()
    return {'items': out}


@router.get('/by-conversation/{conversation_id}')
async def of_conversation(conversation_id: int, who=Depends(reader), session=Depends(get_session)):
    """The funnels a conversation is in, with its stage in each (for the contact file)."""
    from ..whatsapp import api as wa_api
    conversation, registry = await wa_api.access(session, conversation_id, who)
    default = await funnels.ensure_default(session)
    mapping = {s.legacy_stage: s.id for s in await funnels.stages_of(session, default.id)}
    cards = {c.pipeline_id: c for c in (await session.scalars(select(PipelineCard).where(
        PipelineCard.conversation_id == conversation.id))).all()}
    items = [{'pipeline_id': default.id, 'name': default.name, 'default': True,
              'stage_id': mapping.get(stage_of(conversation, registry)),
              'value_cents': int(cards[default.id].value_cents) if default.id in cards else 0}]
    for pipeline in (await session.scalars(select(Pipeline).where(
            Pipeline.archived.is_(False), Pipeline.key.is_(None)).order_by(Pipeline.position))).all():
        card = cards.get(pipeline.id)
        items.append({'pipeline_id': pipeline.id, 'name': pipeline.name, 'default': False,
                      'stage_id': card.stage_id if card else None,
                      'value_cents': int(card.value_cents) if card else 0})
    await session.commit()
    return {'items': items}
