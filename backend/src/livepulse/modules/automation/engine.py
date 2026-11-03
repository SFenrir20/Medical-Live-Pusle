"""Runs the flows (diagrams) when people write.

  * `on_inbound` is registered in the chat core: every incoming message may start ONE flow of its
    channel (the first, by creation order, whose trigger matches). A conversation has at most
    one run per flow at a time.
  * A run walks the diagram node by node and logs each step. A `wait` stores the run; the
    worker (`tick`) resumes it when due.
  * All sending goes through the chat core, so channel policy, caps, opt-outs and the human
    takeover apply. A person writing in the conversation stops the bot there.
  * Test runs (the admin's "Probar" button) use the simulator, skip waits and touch no real
    contact, agent rotation or external system."""
import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from ..chat import hooks
from ..chat.models import ChatConversation, ChatMessage
from ..chat.policy import PolicyViolation
from ..chat.service import (
    SIMULATOR_ID,
    aware,
    bot_may_answer,
    ensure_simulator,
    get_conversation,
    plain,
    send_message,
    utcnow,
    wants_opt_out,
)
from . import ai, graph
from .models import Flow, FlowRun, FlowStep

log = logging.getLogger(__name__)
MAX_STEPS = 60
MAX_RETRIES = 10
RETRY_SECONDS = 30
LIMA = timezone(timedelta(hours=-5))
SYSTEM_ACTOR = 'bot:flow'


@dataclass
class Outcome:
    text: str
    branch: str | None = None
    wait_until: datetime | None = None
    stop: str | None = None            # done | stopped | failed
    reason: str = ''
    same_node: bool = False            # wait, then run this same node again (retry)


@dataclass
class Ctx:
    session: object
    run: FlowRun
    flow: Flow
    conv: ChatConversation
    now: datetime
    fast: bool                          # test run: skip waits and real side effects


def render(text: str, conv: ChatConversation) -> str:
    values = {'nombre': conv.contact_name or '', 'telefono': conv.phone}

    def fill(match):
        return values.get(match.group(1)) or (match.group(2) or '').strip()

    return re.sub(r'\{\{\s*(\w+)\s*(?:\|([^}]*))?\}\}', fill, text).strip()


async def last_inbound_text(session, conv) -> str:
    row = await session.scalar(select(ChatMessage.body).where(
        ChatMessage.conversation_id == conv.id, ChatMessage.direction == 'in')
        .order_by(ChatMessage.id.desc()).limit(1))
    return row or ''


# ---- node executors ------------------------------------------------------------------------

async def _send(ctx: Ctx, node, text: str) -> Outcome | None:
    """Send as the bot. None = sent; otherwise the outcome that ends or delays the run."""
    if not ctx.run.test and not bot_may_answer(ctx.conv, ctx.now):
        return Outcome('detenido: una persona tomó la conversación', stop='stopped',
                       reason='Una persona tomó la conversación.')
    try:
        await send_message(ctx.session, ctx.conv, text, author_kind='bot',
                           author_id=SYSTEM_ACTOR, flow_run_id=ctx.run.id, now=ctx.now)
    except PolicyViolation as problem:
        tries = ctx.run.context.get('retries', 0)
        if problem.retry and not ctx.fast and tries < MAX_RETRIES:
            ctx.run.context = {**ctx.run.context, 'retries': tries + 1}
            return Outcome(f'reintento ({problem.code})',
                           wait_until=ctx.now + timedelta(seconds=RETRY_SECONDS), same_node=True)
        return Outcome(f'bloqueado ({problem.code}): {problem.message}', stop='stopped',
                       reason=problem.message)
    ctx.run.context = {**ctx.run.context, 'retries': 0}
    return None


async def x_trigger(ctx, node):
    return Outcome('inicio')


async def x_send_text(ctx, node):
    text = render(node['config']['text'], ctx.conv)
    problem = await _send(ctx, node, text)
    return problem or Outcome(f'enviado: «{text[:80]}»')


async def x_wait(ctx, node):
    minutes = node['config']['minutes']
    if ctx.fast:
        return Outcome(f'espera de {minutes} min omitida (prueba)')
    return Outcome(f'esperando {minutes} min', wait_until=ctx.now + timedelta(minutes=minutes))


async def x_keyword(ctx, node):
    text = plain(await last_inbound_text(ctx.session, ctx.conv))
    hit = any(plain(w) in text for w in node['config']['keywords'])
    return Outcome('sí' if hit else 'no', branch='yes' if hit else 'no')


async def x_tag_condition(ctx, node):
    hit = node['config']['tag'].strip().lower() in [t.lower() for t in ctx.conv.tags or []]
    return Outcome('sí' if hit else 'no', branch='yes' if hit else 'no')


async def x_status_condition(ctx, node):
    from ..social_live.models import PhoneRegistry
    status = None
    if ctx.conv.registry_id:
        status = await ctx.session.scalar(select(PhoneRegistry.status).where(
            PhoneRegistry.id == ctx.conv.registry_id))
    hit = status in node['config']['statuses']
    return Outcome(f'estado {status or "sin contacto"}: ' + ('sí' if hit else 'no'),
                   branch='yes' if hit else 'no')


async def x_hours(ctx, node):
    config = node['config']
    local = ctx.now.astimezone(LIMA)
    inside = (local.weekday() in config.get('days', [0, 1, 2, 3, 4])
              and config['start'] <= local.strftime('%H:%M') <= config['end'])
    return Outcome('dentro del horario' if inside else 'fuera del horario',
                   branch='yes' if inside else 'no')


async def x_add_tag(ctx, node):
    tag = node['config']['tag'].strip()
    if tag.lower() not in [t.lower() for t in ctx.conv.tags or []]:
        ctx.conv.tags = [*(ctx.conv.tags or []), tag]
    return Outcome(f'etiqueta «{tag}»')


async def x_set_status(ctx, node):
    status = node['config']['status']
    if ctx.fast:
        return Outcome(f'simulado: cambiaría el estado a {status}')
    if not ctx.conv.registry_id:
        return Outcome('omitido: la conversación no está ligada a un contacto')
    from ..social_live import contacts as workflow
    try:
        await workflow.set_status(ctx.session, ctx.conv.registry_id, SYSTEM_ACTOR, status,
                                  manager=True)
    except HTTPException as problem:
        return Outcome(f'no se pudo cambiar el estado: {problem.detail}')
    return Outcome(f'estado → {status}')


async def _assign(ctx: Ctx) -> str:
    """Give the conversation (and its contact, if still free) to the next connected agent."""
    from ..social_live import distribution
    from ..social_live.models import AgentPresence, PhoneRegistry
    agents = await distribution.eligible_agents(ctx.session, ctx.now)
    if not agents:
        return 'ningún agente conectado: queda en espera'
    target = agents[0]
    if ctx.fast:
        return f'simulado: se asignaría a {target}'
    ctx.conv.advisor_id = target
    contact = await ctx.session.get(PhoneRegistry, ctx.conv.registry_id) \
        if ctx.conv.registry_id else None
    if contact is not None and contact.advisor_id is None and contact.status == 'new':
        await distribution.distribute(ctx.session, [contact], ctx.now, 'auto_assign')
    else:
        presence = await ctx.session.get(AgentPresence, target)
        presence.last_assigned_at = ctx.now
    return f'asignada a {target}'


async def x_assign(ctx, node):
    return Outcome(await _assign(ctx))


async def x_handoff(ctx, node):
    text = render(node['config'].get('text', ''), ctx.conv)
    if text:
        await _send(ctx, node, text)  # a blocked courtesy message must not block the handoff
    ctx.conv.bot_active = False
    detail = await _assign(ctx)
    return Outcome(f'pasa a una persona: {detail}', stop='done', reason='Traspasada a una persona.')


async def x_ai_reply(ctx, node):
    try:
        result = await ai.reply_to(ctx.session, ctx.conv, ctx.now)
    except (ai.ProviderError, Exception) as problem:  # noqa: BLE001 - never lose the run
        if isinstance(problem, ai.ProviderError):
            return Outcome(f'error de IA: {problem}', stop='failed', reason=str(problem))
        raise
    if result.text is None:
        return Outcome(f'la IA no respondió ({result.reason})')
    blocked = await _send(ctx, node, result.text)
    if blocked:
        return blocked
    if result.handoff:
        ctx.conv.bot_active = False
        detail = await _assign(ctx)
        return Outcome(f'IA responde y pasa a una persona ({result.reason}): {detail}',
                       stop='done', reason='Traspasada a una persona.')
    return Outcome(f'IA respondió: «{result.text[:80]}»')


def _safe_url(url: str) -> bool:
    host = (urlsplit(url).hostname or '').lower()
    if host in ('localhost',) or host.endswith(('.local', '.internal', '.localhost')):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast)


async def x_webhook(ctx, node):
    url = node['config']['url']
    if ctx.fast:
        return Outcome('simulado: se llamaría al webhook')
    if not _safe_url(url):
        return Outcome('webhook bloqueado: dirección no permitida')
    payload = {'flow': ctx.flow.id, 'phone': ctx.conv.phone, 'name': ctx.conv.contact_name,
               'text': await last_inbound_text(ctx.session, ctx.conv)}
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.post(url, json=payload)
        return Outcome(f'webhook respondió {response.status_code}')
    except httpx.HTTPError as problem:
        return Outcome(f'webhook falló: {type(problem).__name__}')


async def x_end(ctx, node):
    return Outcome('fin', stop='done', reason='Fin del flujo.')


EXECUTORS = {
    'trigger.message': x_trigger, 'trigger.manual': x_trigger,
    'condition.keyword': x_keyword, 'condition.tag': x_tag_condition,
    'condition.status': x_status_condition, 'condition.business_hours': x_hours,
    'action.send_text': x_send_text, 'action.wait': x_wait, 'action.add_tag': x_add_tag,
    'action.set_status': x_set_status, 'action.assign': x_assign,
    'action.handoff': x_handoff, 'action.ai_reply': x_ai_reply, 'action.webhook': x_webhook,
    'action.end': x_end,
}


# ---- running ------------------------------------------------------------------------------

def _finish(run: FlowRun, status: str, reason: str, now: datetime):
    run.status, run.reason, run.finished_at, run.resume_at = status, reason[:300], now, None


async def advance(session, run: FlowRun, flow: Flow, conv: ChatConversation, now: datetime,
                  fast: bool = False) -> None:
    by_id = {n['id']: n for n in flow.graph['nodes']}
    ctx = Ctx(session, run, flow, conv, now, fast)
    run.status = 'running'
    while True:
        if run.steps_count >= MAX_STEPS:
            _finish(run, 'failed', 'Demasiados pasos: se detuvo para evitar un bucle.', now)
            return
        node = by_id.get(run.current_node)
        if node is None:
            _finish(run, 'failed', 'El flujo cambió y el paso ya no existe.', now)
            return
        outcome = await EXECUTORS[node['type']](ctx, node)
        run.steps_count += 1
        session.add(FlowStep(run_id=run.id, node_id=node['id'], node_type=node['type'],
                             outcome=outcome.text[:300], created_at=now))
        if outcome.stop:
            _finish(run, outcome.stop, outcome.reason, now)
            return
        if outcome.same_node:
            run.status, run.resume_at = 'waiting', outcome.wait_until
            return
        following = graph.next_nodes(flow.graph, node['id'], outcome.branch)
        if not following:
            _finish(run, 'done', 'Fin del flujo.', now)
            return
        run.current_node = following[0]
        if outcome.wait_until:
            run.status, run.resume_at = 'waiting', outcome.wait_until
            return


async def start_run(session, flow: Flow, conv: ChatConversation, now: datetime, *,
                    text: str = '', test: bool = False) -> FlowRun:
    trigger = graph.trigger_of(flow.graph)
    run = FlowRun(flow_id=flow.id, conversation_id=conv.id, status='running',
                  current_node=trigger['id'], context={'text': text}, test=test, started_at=now)
    session.add(run)
    await session.flush()
    await advance(session, run, flow, conv, now, fast=test)
    return run


def _matches(trigger: dict, text: str) -> bool:
    if trigger['type'] != 'trigger.message':
        return False
    config = trigger.get('config') or {}
    if config.get('match', 'any') == 'any':
        return True
    cleaned = plain(text)
    return any(plain(word) in cleaned for word in config.get('keywords', []))


async def on_inbound(session, conversation: ChatConversation, message: ChatMessage) -> None:
    """Chat-core hook: an incoming message may start one flow of that channel."""
    now = aware(message.created_at) or utcnow()
    if wants_opt_out(message.body) or not bot_may_answer(conversation, now):
        return
    flows = (await session.scalars(select(Flow).where(
        Flow.channel_id == conversation.channel_id, Flow.enabled.is_(True))
        .order_by(Flow.id))).all()
    for flow in flows:
        if graph.validate(flow.graph) or not _matches(graph.trigger_of(flow.graph), message.body):
            continue
        busy = await session.scalar(select(FlowRun.id).where(
            FlowRun.flow_id == flow.id, FlowRun.conversation_id == conversation.id,
            FlowRun.status.in_(('running', 'waiting'))))
        if busy:
            continue
        await start_run(session, flow, conversation, utcnow(), text=message.body)
        return  # one flow answers each message


async def run_test(session, flow: Flow, text: str, phone: str = '+51999000000',
                   name: str = 'Paciente de prueba') -> tuple[FlowRun, list[ChatMessage]]:
    """The admin's test: a pretend patient writes on the SIMULATOR and the flow runs now."""
    now = utcnow()
    await ensure_simulator(session)
    conv = await get_conversation(session, SIMULATOR_ID, phone, name)
    inbound = ChatMessage(conversation_id=conv.id, direction='in', author_kind='contact',
                          body=text[:4000], status='received', created_at=now)
    session.add(inbound)
    conv.last_inbound_at, conv.last_message_at = now, now
    conv.bot_active, conv.bot_paused_until = True, None
    await session.flush()
    run = await start_run(session, flow, conv, now, text=text, test=True)
    sent = (await session.scalars(select(ChatMessage).where(
        ChatMessage.flow_run_id == run.id).order_by(ChatMessage.id))).all()
    return run, list(sent)


async def tick(factory, now: datetime | None = None) -> int:
    """Resume the runs whose wait is over."""
    now = now or utcnow()
    resumed = 0
    async with factory() as session, session.begin():
        runs = (await session.scalars(select(FlowRun).where(
            FlowRun.status == 'waiting', FlowRun.resume_at <= now)
            .order_by(FlowRun.resume_at).limit(50).with_for_update(skip_locked=True))).all()
        for run in runs:
            flow = await session.get(Flow, run.flow_id)
            conv = await session.get(ChatConversation, run.conversation_id)
            if not flow.enabled and not run.test:
                _finish(run, 'stopped', 'El flujo se apagó mientras esperaba.', now)
                continue
            await advance(session, run, flow, conv, now, fast=run.test)
            resumed += 1
    return resumed


hooks.register_inbound(on_inbound)
