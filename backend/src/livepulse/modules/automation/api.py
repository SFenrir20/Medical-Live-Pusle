"""Admin API of the automation tools: channels and their safety policy, flows, the AI agent and
broadcasts.

`automation:manage` (admin only) creates, edits, enables and sends. `automation:read` (supervisor,
marketing head, manager) only looks: flows, AI settings without the key, and broadcast counts.
Phones and conversations are never in a read-only response. Every change by an admin is written
to automation_audit."""
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, select

from ...shared import crypto
from ...shared.db import get_session
from ..chat import policy
from ..chat.channels import CAPABILITIES
from ..chat.models import CHANNEL_KINDS, ChatChannel
from ..chat.policy import PolicyViolation
from ..identity.roles import permissions_of
from ..social_live import queries
from ..social_live.security import require_scope
from . import ai, broadcasts, engine, graph
from .models import (
    AiAgent,
    AiKnowledgeDoc,
    AiUsage,
    AutomationAudit,
    Broadcast,
    BroadcastRecipient,
    Flow,
    FlowRun,
    FlowStep,
    StudioSetting,
)

router = APIRouter(prefix='/api/automation', tags=['automation'])
reader = require_scope('automation:read', 'automation:manage')
manager = require_scope('automation:manage')
SLUG = re.compile(r'^[a-z0-9_-]{2,32}$')


def iso(value):
    return queries.iso(engine.aware(value)) if value is not None else None


def audit(session, who, action: str, entity: str, entity_id=None, detail=None):
    session.add(AutomationAudit(actor=who['user_id'], action=action, entity=entity,
                                entity_id=str(entity_id) if entity_id is not None else None,
                                detail=detail))


async def _get(session, model, row_id, what: str):
    row = await session.get(model, row_id)
    if row is None:
        raise HTTPException(404, f'{what} no encontrado.')
    return row


# ---- overview and channels --------------------------------------------------------------


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='Contáctanos', min_length=1, max_length=80)
    subtitle: str = Field(default='¿Cuál es la mejor manera para contactarte?', max_length=160)
    color: str = Field(default='#0f92ac', pattern=r'^#[0-9a-fA-F]{6}$')
    text_color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    position: Literal['left', 'right'] = 'right'
    whatsapp: str = Field(default='', pattern=r'^(\+[1-9][0-9]{7,14})?$')
    instagram: str = Field(default='', pattern=r'^[A-Za-z0-9._]{0,60}$')
    messenger: str = Field(default='', pattern=r'^[A-Za-z0-9._-]{0,60}$')
    whatsapp_enabled: bool = True
    instagram_enabled: bool = False
    messenger_enabled: bool = False


@router.get('/studio/widget')
async def get_widget(who=Depends(reader), session=Depends(get_session)):
    row = await session.get(StudioSetting, 'widget')
    return row.value if row else WidgetConfig().model_dump()


@router.put('/studio/widget')
async def save_widget(body: WidgetConfig, who=Depends(manager), session=Depends(get_session)):
    row = await session.get(StudioSetting, 'widget')
    if row is None:
        row = StudioSetting(id='widget')
        session.add(row)
    row.value, row.updated_by, row.updated_at = body.model_dump(), who['user_id'], engine.utcnow()
    audit(session, who, 'update', 'widget', 'widget')
    await session.commit()
    return row.value


PRESET_TITLES = {'welcome': 'Mensaje de bienvenida', 'lead': 'Mensaje para leads',
                 'appointment': 'Recordatorio de cita', 'followup': 'Seguimiento posterior'}


class MessagePreset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: Literal['welcome', 'lead', 'appointment', 'followup']
    text: str = Field(min_length=1, max_length=500)
    enabled: bool = True
    delay_minutes: int = Field(default=0, ge=0, le=10080)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.text.strip():
            raise ValueError('El mensaje no puede estar vacío.')
        return self


class PresetsIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[MessagePreset] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def unique_presets(self):
        if {item.key for item in self.items} != set(PRESET_TITLES):
            raise ValueError('Incluye una vez cada uno de los cuatro mensajes.')
        return self


@router.get('/studio/messages')
async def get_presets(who=Depends(reader), session=Depends(get_session)):
    row = await session.get(StudioSetting, 'messages')
    return row.value if row else {'items': []}


@router.put('/studio/messages')
async def save_presets(body: PresetsIn, who=Depends(manager), session=Depends(get_session)):
    from ..chat.service import ensure_simulator
    channel = await ensure_simulator(session)
    row = await session.get(StudioSetting, 'messages')
    previous = {item['key']: item for item in (row.value.get('items', []) if row else [])}
    saved = []
    for item in body.items:
        existing = previous.get(item.key, {}).get('flow_id')
        flow = await session.get(Flow, existing) if existing else None
        if flow is None:
            flow = Flow(name=PRESET_TITLES[item.key], channel_id=channel.id,
                        created_by=who['user_id'], graph={})
            session.add(flow)
        # Saving a preset never activates an automation on a real channel.
        nodes = [{'id': 'inicio', 'type': 'trigger.message' if item.key == 'welcome'
                  else 'trigger.manual', 'config': {'match': 'any'}, 'pos': {'x': 40, 'y': 100}}]
        if item.enabled:
            if item.delay_minutes:
                nodes.append({'id': 'espera', 'type': 'action.wait',
                              'config': {'minutes': item.delay_minutes}, 'pos': {'x': 300, 'y': 100}})
            nodes.append({'id': 'mensaje', 'type': 'action.send_text', 'config': {'text': item.text},
                          'pos': {'x': 560, 'y': 100}})
        nodes.append({'id': 'fin', 'type': 'action.end', 'config': {}, 'pos': {'x': 820, 'y': 100}})
        flow.graph = {'nodes': nodes, 'edges': [{'from': a['id'], 'to': b['id']}
                      for a, b in zip(nodes, nodes[1:], strict=False)]}
        flow.channel_id, flow.enabled = channel.id, False
        flow.version = (flow.version or 0) + 1
        flow.updated_at = engine.utcnow()
        flow.description = 'MedicalBot: preset en simulador. No conectado a citas ni envíos reales.'
        await session.flush()
        saved.append({**item.model_dump(), 'flow_id': flow.id})
    if row is None:
        row = StudioSetting(id='messages')
        session.add(row)
    row.value, row.updated_by, row.updated_at = {'items': saved}, who['user_id'], engine.utcnow()
    audit(session, who, 'update', 'message-presets', 'messages')
    await session.commit()
    return row.value

def channel_item(channel: ChatChannel) -> dict:
    capabilities = CAPABILITIES[channel.kind]
    return {'id': channel.id, 'kind': channel.kind, 'name': channel.name,
            'status': channel.status, **policy.describe(channel),
            'capabilities': {'free_text_anytime': capabilities.free_text_anytime,
                             'templates': capabilities.templates}}


@router.get('/overview')
async def overview(who=Depends(reader), session=Depends(get_session)):
    from ..chat.service import ensure_simulator
    await ensure_simulator(session)
    await session.commit()
    channels = (await session.scalars(select(ChatChannel).order_by(ChatChannel.id))).all()
    agent = await ai.get_agent(session)
    flows = (await session.execute(select(Flow.enabled, func.count()).group_by(Flow.enabled))).all()
    active = await session.scalar(select(func.count()).select_from(Broadcast).where(
        Broadcast.status.in_(('scheduled', 'sending')))) or 0
    return {
        'channels': [channel_item(c) for c in channels],
        'flows': {'enabled': dict(flows).get(True, 0), 'disabled': dict(flows).get(False, 0)},
        'ai': {'enabled': agent.enabled, 'provider': agent.provider, 'has_key': bool(
            agent.api_key_encrypted)},
        'broadcasts_active': active,
        'catalog': {k: {'label': v[0], 'help': v[1]} for k, v in graph.CATALOG.items()},
        'providers': list(ai.PROVIDERS), 'suggested_models': ai.SUGGESTED_MODELS,
        'can_manage': 'automation:manage' in permissions_of(who.get('role'))}


class ChannelIn(BaseModel):
    id: str
    kind: Literal['simulator', 'whatsapp_mirror', 'whatsapp_cloud']
    name: str = Field(min_length=1, max_length=100)


@router.post('/channels', status_code=201)
async def create_channel(body: ChannelIn, who=Depends(manager), session=Depends(get_session)):
    """Register a channel before its gateway exists, so its policy can be set up first."""
    if not SLUG.match(body.id) or body.kind not in CHANNEL_KINDS:
        raise HTTPException(422, 'Id de canal inválido (2 a 32 letras minúsculas, números, - o _).')
    if await session.get(ChatChannel, body.id) is not None:
        raise HTTPException(409, 'Ya existe un canal con ese id.')
    channel = ChatChannel(id=body.id, kind=body.kind, name=body.name.strip(), policy={})
    session.add(channel)
    audit(session, who, 'create', 'channel', body.id, {'kind': body.kind})
    await session.commit()
    return channel_item(channel)


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal['active', 'disabled'] | None = None
    policy: dict | None = None
    # Turning bots or mass messages ON for a channel with ban risk needs this, on purpose.
    acknowledge_risk: bool = False


@router.patch('/channels/{channel_id}')
async def patch_channel(channel_id: str, body: ChannelPatch, who=Depends(manager),
                        session=Depends(get_session)):
    channel = await _get(session, ChatChannel, channel_id, 'Canal')
    if body.name:
        channel.name = body.name.strip()
    if body.status:
        channel.status = body.status
    if body.policy is not None:
        try:
            overrides = policy.clean_overrides(body.policy)
        except (ValueError, TypeError) as problem:
            raise HTTPException(422, str(problem)) from None
        before = policy.effective(channel)
        merged = {**(channel.policy or {}), **overrides}
        turning_on = any(overrides.get(k) and not before[k]
                         for k in ('bots_enabled', 'broadcasts_enabled'))
        if turning_on and CAPABILITIES[channel.kind].risky_automation and not body.acknowledge_risk:
            raise HTTPException(422, 'Este canal no es el oficial de WhatsApp: los bots y los '
                                     'mensajes masivos pueden hacer que restrinjan o bloqueen '
                                     'el número. Confirma que entiendes el riesgo.')
        channel.policy = merged
        audit(session, who, 'policy', 'channel', channel_id,
              {'changed': overrides, 'acknowledged_risk': body.acknowledge_risk})
    await session.commit()
    return channel_item(channel)


# ---- flows ---------------------------------------------------------------------------------

class FlowIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    channel_id: str
    graph: dict


def flow_item(flow: Flow, full: bool = False) -> dict:
    errors = graph.validate(flow.graph)
    item = {'id': flow.id, 'name': flow.name, 'description': flow.description,
            'channel_id': flow.channel_id, 'enabled': flow.enabled, 'version': flow.version,
            'valid': not errors, 'updated_at': iso(flow.updated_at)}
    if full:
        item.update(graph=flow.graph, errors=errors)
    return item


@router.get('/flows')
async def list_flows(who=Depends(reader), session=Depends(get_session)):
    rows = (await session.scalars(select(Flow).order_by(Flow.id))).all()
    return {'items': [flow_item(f) for f in rows]}


@router.post('/flows', status_code=201)
async def create_flow(body: FlowIn, who=Depends(manager), session=Depends(get_session)):
    await _get(session, ChatChannel, body.channel_id, 'Canal')
    now = engine.utcnow()
    flow = Flow(name=body.name.strip(), description=body.description, channel_id=body.channel_id,
                graph=body.graph, enabled=False, created_by=who['user_id'], created_at=now,
                updated_at=now)
    session.add(flow)
    await session.flush()
    audit(session, who, 'create', 'flow', flow.id)
    await session.commit()
    return flow_item(flow, full=True)


@router.get('/flows/{flow_id}')
async def get_flow(flow_id: int, who=Depends(reader), session=Depends(get_session)):
    return flow_item(await _get(session, Flow, flow_id, 'Flujo'), full=True)


@router.put('/flows/{flow_id}')
async def update_flow(flow_id: int, body: FlowIn, who=Depends(manager),
                      session=Depends(get_session)):
    flow = await _get(session, Flow, flow_id, 'Flujo')
    await _get(session, ChatChannel, body.channel_id, 'Canal')
    errors = graph.validate(body.graph)
    if flow.enabled and errors:
        raise HTTPException(422, {'message': 'Un flujo activo debe ser válido. Apágalo para '
                                             'guardar cambios incompletos.', 'errors': errors})
    flow.name, flow.description = body.name.strip(), body.description
    flow.channel_id, flow.graph = body.channel_id, body.graph
    flow.version += 1
    flow.updated_at = engine.utcnow()
    audit(session, who, 'update', 'flow', flow_id, {'version': flow.version})
    await session.commit()
    return flow_item(flow, full=True)


@router.post('/flows/{flow_id}/enable')
async def enable_flow(flow_id: int, who=Depends(manager), session=Depends(get_session)):
    flow = await _get(session, Flow, flow_id, 'Flujo')
    errors = graph.validate(flow.graph)
    if errors:
        raise HTTPException(422, {'message': 'El flujo tiene errores.', 'errors': errors})
    channel = await session.get(ChatChannel, flow.channel_id)
    warnings = []
    if channel.status != 'active':
        warnings.append('El canal está deshabilitado: el flujo no enviará nada.')
    if not policy.effective(channel)['bots_enabled']:
        warnings.append('Los bots están apagados en este canal: el flujo se ejecutará pero sus '
                        'mensajes quedarán bloqueados hasta encenderlos en la política del canal.')
    flow.enabled = True
    audit(session, who, 'enable', 'flow', flow_id, {'warnings': warnings})
    await session.commit()
    return {**flow_item(flow), 'warnings': warnings}


@router.post('/flows/{flow_id}/disable')
async def disable_flow(flow_id: int, who=Depends(manager), session=Depends(get_session)):
    flow = await _get(session, Flow, flow_id, 'Flujo')
    flow.enabled = False
    audit(session, who, 'disable', 'flow', flow_id)
    await session.commit()
    return flow_item(flow)


@router.delete('/flows/{flow_id}', status_code=204)
async def delete_flow(flow_id: int, who=Depends(manager), session=Depends(get_session)):
    flow = await _get(session, Flow, flow_id, 'Flujo')
    if flow.enabled:
        raise HTTPException(409, 'Apaga el flujo antes de borrarlo.')
    runs = select(FlowRun.id).where(FlowRun.flow_id == flow_id)
    await session.execute(delete(FlowStep).where(FlowStep.run_id.in_(runs)))
    await session.execute(delete(FlowRun).where(FlowRun.flow_id == flow_id))
    await session.delete(flow)
    audit(session, who, 'delete', 'flow', flow_id)
    await session.commit()


class TestIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    phone: str = Field(default='+51999000000', max_length=20)


def run_item(run: FlowRun, steps=None) -> dict:
    item = {'id': run.id, 'flow_id': run.flow_id, 'conversation_id': run.conversation_id,
            'status': run.status, 'reason': run.reason, 'test': run.test,
            'steps_count': run.steps_count, 'started_at': iso(run.started_at),
            'finished_at': iso(run.finished_at)}
    if steps is not None:
        item['steps'] = [{'node_id': s.node_id, 'type': s.node_type, 'outcome': s.outcome,
                          'at': iso(s.created_at)} for s in steps]
    return item


@router.post('/flows/{flow_id}/test')
async def test_flow(flow_id: int, body: TestIn, who=Depends(manager),
                    session=Depends(get_session)):
    """Run the flow now against the simulator with a pretend patient: waits are skipped and no
    real contact, agent or external system is touched."""
    flow = await _get(session, Flow, flow_id, 'Flujo')
    errors = graph.validate(flow.graph)
    if errors:
        raise HTTPException(422, {'message': 'El flujo tiene errores.', 'errors': errors})
    try:
        run, sent = await engine.run_test(session, flow, body.text, body.phone)
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    steps = (await session.scalars(select(FlowStep).where(FlowStep.run_id == run.id)
                                   .order_by(FlowStep.id))).all()
    audit(session, who, 'test', 'flow', flow_id)
    await session.commit()
    return {**run_item(run, steps), 'messages': [
        {'body': m.body, 'status': m.status, 'error': m.error} for m in sent]}


@router.get('/flows/{flow_id}/runs')
async def flow_runs(flow_id: int, limit: int = Query(30, ge=1, le=100), who=Depends(reader),
                    session=Depends(get_session)):
    await _get(session, Flow, flow_id, 'Flujo')
    rows = (await session.scalars(select(FlowRun).where(FlowRun.flow_id == flow_id)
                                  .order_by(FlowRun.id.desc()).limit(limit))).all()
    return {'items': [run_item(r) for r in rows]}


@router.get('/runs/{run_id}')
async def get_run(run_id: int, who=Depends(reader), session=Depends(get_session)):
    run = await _get(session, FlowRun, run_id, 'Ejecución')
    steps = (await session.scalars(select(FlowStep).where(FlowStep.run_id == run_id)
                                   .order_by(FlowStep.id))).all()
    return run_item(run, steps)


# ---- AI agent -----------------------------------------------------------------------------

def agent_item(agent: AiAgent) -> dict:
    key = None
    if agent.api_key_encrypted:
        try:
            key = crypto.mask(crypto.decrypt(agent.api_key_encrypted))
        except crypto.SecretsUnavailable:
            key = '(ilegible)'
    return {'enabled': agent.enabled, 'provider': agent.provider, 'model': agent.model,
            'base_url': agent.base_url, 'has_key': bool(agent.api_key_encrypted), 'key_hint': key,
            'name': agent.name, 'clinic_name': agent.clinic_name,
            'instructions': agent.instructions, 'knowledge_only': agent.knowledge_only,
            'handoff_keywords': agent.handoff_keywords or [],
            'handoff_message': agent.handoff_message, 'max_replies': agent.max_replies,
            'daily_message_cap': agent.daily_message_cap, 'updated_at': iso(agent.updated_at)}


@router.get('/ai/config')
async def get_ai(who=Depends(reader), session=Depends(get_session)):
    agent = await ai.get_agent(session)
    await session.commit()
    return agent_item(agent)


class AiConfigIn(BaseModel):
    enabled: bool | None = None
    provider: Literal['echo', 'anthropic', 'openai', 'openai_compatible'] | None = None
    model: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=300)   # '' keeps the stored one
    clear_key: bool = False
    name: str | None = Field(default=None, min_length=1, max_length=60)
    clinic_name: str | None = Field(default=None, min_length=1, max_length=80)
    instructions: str | None = Field(default=None, max_length=4000)
    knowledge_only: bool | None = None
    handoff_keywords: list[str] | None = Field(default=None, max_length=60)
    handoff_message: str | None = Field(default=None, max_length=300)
    max_replies: int | None = Field(default=None, ge=1, le=50)
    daily_message_cap: int | None = Field(default=None, ge=1, le=100000)


@router.put('/ai/config')
async def put_ai(body: AiConfigIn, who=Depends(manager), session=Depends(get_session)):
    agent = await ai.get_agent(session)
    data = body.model_dump(exclude_none=True)
    key = data.pop('api_key', '')
    clear = data.pop('clear_key', False)
    if 'handoff_keywords' in data:
        data['handoff_keywords'] = sorted({w.strip().lower()[:40] for w in data['handoff_keywords']
                                           if w.strip()})
    for field, value in data.items():
        setattr(agent, field, value)
    try:
        if clear:
            agent.api_key_encrypted = None
        elif key.strip():
            agent.api_key_encrypted = crypto.encrypt(key.strip())
    except crypto.SecretsUnavailable as problem:
        raise HTTPException(503, str(problem)) from None
    if agent.enabled and agent.provider != 'echo' and not (agent.api_key_encrypted and agent.model):
        raise HTTPException(422, 'Para activar un proveedor real indica la clave y el modelo.')
    agent.updated_by, agent.updated_at = who['user_id'], engine.utcnow()
    audit(session, who, 'config', 'ai', 1, {'fields': sorted(data), 'key_changed': bool(
        key.strip() or clear), 'enabled': agent.enabled, 'provider': agent.provider})
    await session.commit()
    return agent_item(agent)


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=20000)
    active: bool = True


def knowledge_item(doc: AiKnowledgeDoc) -> dict:
    return {'id': doc.id, 'title': doc.title, 'body': doc.body, 'active': doc.active,
            'created_at': iso(doc.created_at)}


@router.get('/ai/knowledge')
async def list_knowledge(who=Depends(reader), session=Depends(get_session)):
    rows = (await session.scalars(select(AiKnowledgeDoc).order_by(AiKnowledgeDoc.id))).all()
    return {'items': [knowledge_item(d) for d in rows]}


@router.post('/ai/knowledge', status_code=201)
async def add_knowledge(body: KnowledgeIn, who=Depends(manager), session=Depends(get_session)):
    doc = AiKnowledgeDoc(title=body.title.strip(), body=body.body.strip(), active=body.active,
                         created_at=engine.utcnow())
    session.add(doc)
    await session.flush()
    audit(session, who, 'create', 'knowledge', doc.id)
    await session.commit()
    return knowledge_item(doc)


@router.put('/ai/knowledge/{doc_id}')
async def edit_knowledge(doc_id: int, body: KnowledgeIn, who=Depends(manager),
                         session=Depends(get_session)):
    doc = await _get(session, AiKnowledgeDoc, doc_id, 'Documento')
    doc.title, doc.body, doc.active = body.title.strip(), body.body.strip(), body.active
    audit(session, who, 'update', 'knowledge', doc_id)
    await session.commit()
    return knowledge_item(doc)


@router.delete('/ai/knowledge/{doc_id}', status_code=204)
async def delete_knowledge(doc_id: int, who=Depends(manager), session=Depends(get_session)):
    doc = await _get(session, AiKnowledgeDoc, doc_id, 'Documento')
    await session.delete(doc)
    audit(session, who, 'delete', 'knowledge', doc_id)
    await session.commit()


class PlaygroundIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=20)


@router.post('/ai/playground')
async def playground(body: PlaygroundIn, who=Depends(manager), session=Depends(get_session)):
    """Try the agent with a made-up conversation. Nothing is sent to anyone and nothing counts
    against the daily cap; a real provider IS called if one is configured (it costs tokens)."""
    history = []
    for item in body.messages:
        role = 'assistant' if item.get('role') == 'assistant' else 'user'
        text = str(item.get('content', '')).strip()[:2000]
        if text:
            if history and history[-1]['role'] == role:
                history[-1]['content'] += '\n' + text
            else:
                history.append({'role': role, 'content': text})
    while history and history[0]['role'] != 'user':
        history.pop(0)
    if not history or history[-1]['role'] != 'user':
        raise HTTPException(422, 'La conversación debe terminar con un mensaje de la persona.')
    agent = await ai.get_agent(session)
    try:
        result = await ai.answer(session, agent, history, engine.utcnow(), count_usage=False)
    except (ai.ProviderError, crypto.SecretsUnavailable) as problem:
        raise HTTPException(502, str(problem)) from None
    return {'text': result.text, 'handoff': result.handoff, 'reason': result.reason,
            'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens}


@router.get('/ai/usage')
async def ai_usage(who=Depends(reader), session=Depends(get_session)):
    rows = (await session.scalars(select(AiUsage).order_by(AiUsage.day.desc()).limit(14))).all()
    return {'items': [{'day': r.day, 'messages': r.messages, 'input_tokens': r.input_tokens,
                       'output_tokens': r.output_tokens} for r in rows]}


# ---- broadcasts ---------------------------------------------------------------------------

class AudienceIn(BaseModel):
    audience: dict = Field(default_factory=dict)


class BroadcastIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel_id: str
    body: str = Field(min_length=1, max_length=1000)
    audience: dict = Field(default_factory=dict)


def broadcast_item(b: Broadcast) -> dict:
    return {'id': b.id, 'name': b.name, 'channel_id': b.channel_id, 'body': b.body,
            'audience': b.audience, 'status': b.status, 'pause_reason': b.pause_reason,
            'scheduled_at': iso(b.scheduled_at), 'total': b.total, 'sent': b.sent,
            'failed': b.failed, 'skipped': b.skipped, 'created_by': b.created_by,
            'created_at': iso(b.created_at), 'started_at': iso(b.started_at),
            'finished_at': iso(b.finished_at)}


@router.get('/broadcasts')
async def list_broadcasts(who=Depends(reader), session=Depends(get_session)):
    rows = (await session.scalars(select(Broadcast).order_by(Broadcast.id.desc()).limit(50))).all()
    return {'items': [broadcast_item(b) for b in rows]}


@router.post('/broadcasts/preview')
async def preview_broadcast(body: AudienceIn, who=Depends(manager), session=Depends(get_session)):
    try:
        return await broadcasts.preview(session, body.audience)
    except (ValueError, TypeError) as problem:
        raise HTTPException(422, str(problem)) from None


@router.post('/broadcasts', status_code=201)
async def create_broadcast(body: BroadcastIn, who=Depends(manager),
                           session=Depends(get_session)):
    try:
        broadcast = await broadcasts.create(session, who['user_id'], body.name, body.channel_id,
                                            body.body, body.audience)
    except (ValueError, TypeError) as problem:
        raise HTTPException(422, str(problem)) from None
    audit(session, who, 'create', 'broadcast', broadcast.id, {'total': broadcast.total})
    await session.commit()
    return broadcast_item(broadcast)


@router.get('/broadcasts/{broadcast_id}')
async def get_broadcast(broadcast_id: int, who=Depends(reader), session=Depends(get_session)):
    broadcast = await _get(session, Broadcast, broadcast_id, 'Difusión')
    item = broadcast_item(broadcast)
    counts = dict((await session.execute(
        select(BroadcastRecipient.status, func.count()).where(
            BroadcastRecipient.broadcast_id == broadcast_id)
        .group_by(BroadcastRecipient.status))).all())
    item['recipients_by_status'] = counts
    if 'automation:manage' in permissions_of(who.get('role')):  # phones only for the admin
        rows = (await session.scalars(select(BroadcastRecipient).where(
            BroadcastRecipient.broadcast_id == broadcast_id)
            .order_by(BroadcastRecipient.id).limit(100))).all()
        item['recipients'] = [{'phone': r.phone, 'name': r.name, 'status': r.status,
                               'error': r.error, 'sent_at': iso(r.sent_at)} for r in rows]
    return item


class TestSendIn(BaseModel):
    phone: str = Field(min_length=6, max_length=20)


@router.post('/broadcasts/{broadcast_id}/test')
async def test_broadcast(broadcast_id: int, body: TestSendIn, who=Depends(manager),
                         session=Depends(get_session)):
    broadcast = await _get(session, Broadcast, broadcast_id, 'Difusión')
    try:
        message = await broadcasts.test_send(session, broadcast, body.phone)
    except PolicyViolation as problem:
        await session.commit()
        raise HTTPException(409, problem.message) from None
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    audit(session, who, 'test', 'broadcast', broadcast_id)
    await session.commit()
    return {'sent': True, 'body': message.body}


class StartIn(BaseModel):
    confirm_total: int
    scheduled_at: datetime | None = None


@router.post('/broadcasts/{broadcast_id}/start')
async def start_broadcast(broadcast_id: int, body: StartIn, who=Depends(manager),
                          session=Depends(get_session)):
    broadcast = await _get(session, Broadcast, broadcast_id, 'Difusión')
    try:
        await broadcasts.start(session, broadcast, body.confirm_total, body.scheduled_at)
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    audit(session, who, 'start', 'broadcast', broadcast_id,
          {'total': broadcast.total, 'scheduled_at': iso(broadcast.scheduled_at)})
    await session.commit()
    return broadcast_item(broadcast)


@router.post('/broadcasts/{broadcast_id}/{action}')
async def broadcast_action(broadcast_id: int, action: Literal['pause', 'resume', 'cancel'],
                           who=Depends(manager), session=Depends(get_session)):
    broadcast = await _get(session, Broadcast, broadcast_id, 'Difusión')
    try:
        await broadcasts.set_state(session, broadcast, action)
    except ValueError as problem:
        raise HTTPException(409, str(problem)) from None
    audit(session, who, action, 'broadcast', broadcast_id)
    await session.commit()
    return broadcast_item(broadcast)


@router.get('/audit')
async def audit_log(limit: int = Query(50, ge=1, le=200), who=Depends(manager),
                    session=Depends(get_session)):
    rows = (await session.scalars(select(AutomationAudit).order_by(AutomationAudit.id.desc())
                                  .limit(limit))).all()
    return {'items': [{'id': r.id, 'actor': r.actor, 'action': r.action, 'entity': r.entity,
                       'entity_id': r.entity_id, 'detail': r.detail, 'at': iso(r.created_at)}
                      for r in rows]}
