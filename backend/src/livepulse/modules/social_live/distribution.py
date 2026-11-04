"""Who is connected, and automatic distribution of new contacts among them.

The idea: contacts do not sit in a common pool for agents to grab. They are PUSHED, in rotation,
to the agents who are connected right now.

  * The open app of an agent sends a heartbeat every ~20 s. No heartbeat for
    PRESENCE_OFFLINE_AFTER_S = disconnected (red light). An agent can also pause (amber): she stays
    signed in but receives nothing.
  * Round robin by `last_assigned_at`: the next contact goes to the connected agent who has gone
    longest without one. Someone who joins gets the next one; someone who leaves simply drops out
    of the rotation. Nothing is rebalanced when a person joins: only new contacts flow to her.
  * A contact nobody has worked yet (status `new`) must not wait for a disconnected agent: after
    REDISTRIBUTE_GRACE_S (or at once when she pauses) it is handed to the connected ones. If
    nobody is connected it returns to the pool and goes out as soon as someone connects.
  * Contacts already being worked (contacted, qualified, discarded) stay with their agent.
  * The same heartbeats measure how long each agent has the CRM open (connected) and in front of
    her (active), per session.

Every move is a conditional UPDATE (it only applies if the contact is still as it was read), so
two workers or a manual change can never double-assign. Each move is written to contact_audit
with the actor `system:auto`. Switch off with AUTO_ASSIGNMENT=false (back to self-service)."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, update

from ...shared.config import settings
from ...shared.db import get_session
from ..analytics.models import UserRole
from . import queries
from .leads import names_of
from .models import AgentPresence, AgentSession, PhoneRegistry
from .security import require_scope
from .service import audit, aware_utc, utcnow

router = APIRouter(prefix='/api/presence', tags=['presence'])
AGENT_ROLE = 'agente_ventas'
SYSTEM_ACTOR = 'system:auto'
POOL_BATCH = 200
LIMA = timezone(timedelta(hours=-5))

worker_scope = require_scope('contacts:read')
manager_scope = require_scope('alerts:read', 'contacts:read_all')


def offline_after() -> timedelta:
    return timedelta(seconds=settings.presence_offline_after_s)


IDLE_DISCONNECT = timedelta(minutes=15)


def is_online(row: AgentPresence, now: datetime) -> bool:
    return (not row.reconnect_required and row.last_heartbeat_at is not None
            and aware_utc(row.last_heartbeat_at) >= now - offline_after()
            and not (row.idle_since and now >= aware_utc(row.idle_since) + IDLE_DISCONNECT))


def is_eligible(row: AgentPresence, now: datetime) -> bool:
    return (row.role == AGENT_ROLE and row.status == 'available'
            and row.idle_since is None and is_online(row, now))


def state_of(row: AgentPresence | None, now: datetime) -> str:
    if row is None or not is_online(row, now):
        return 'offline'
    return 'paused' if row.status == 'paused' or row.idle_since else 'online'


async def heartbeat(session, user_id: str, role: str, visible: bool, now: datetime | None = None,
                    status: str | None = None) -> bool:
    """Yellow keeps the session; red is latched until an explicit Connect action."""
    now = now or utcnow()
    row = await session.get(AgentPresence, user_id, with_for_update=True)
    fresh = row is None
    if fresh:
        row = AgentPresence(user_id=user_id, role=role, status='available')
        session.add(row)
        await session.flush()
    was_online = is_online(row, now)
    previous_green = row.status == 'available' and row.idle_since is None
    current = await session.scalar(select(AgentSession).where(
        AgentSession.user_id == user_id, AgentSession.ended_at.is_(None))
        .order_by(AgentSession.id.desc()).limit(1))
    # Account only the bounded interval since the previous beat, in its previous state.
    if current:
        end = now
        if not fresh and not was_online:
            end = aware_utc(current.last_heartbeat_at)
            if row.idle_since:
                end = min(now, aware_utc(row.idle_since) + IDLE_DISCONNECT,
                          aware_utc(current.last_heartbeat_at) + offline_after())
        seconds = max(0, min((end - aware_utc(current.last_heartbeat_at)).total_seconds(),
                             offline_after().total_seconds()))
        current.connected_seconds += round(seconds)
        if previous_green:
            current.active_seconds += round(seconds)
        current.last_heartbeat_at = end
        if not was_online or status == 'offline':
            current.ended_at = end
            current = None
    if not fresh and not was_online:
        row.reconnect_required = True
    if row.reconnect_required or status == 'offline':
        row.status = 'paused'
    if status == 'offline':
        row.reconnect_required = True
    elif status == 'available':
        row.reconnect_required = False
        row.status = 'available'
        row.idle_since = None
    elif status == 'paused':
        row.status = 'paused'
    row.role = role
    row.last_heartbeat_at = now
    if not row.reconnect_required:
        if visible and row.status == 'available':
            row.last_visible_at = now
            row.idle_since = None
        elif row.idle_since is None:
            row.idle_since = now
        if current is None:
            session.add(AgentSession(user_id=user_id, started_at=now, last_heartbeat_at=now))
    return not was_online and is_online(row, now)


async def close_stale_sessions(session, now: datetime):
    rows = (await session.scalars(select(AgentPresence).with_for_update())).all()
    for row in rows:
        if is_online(row, now):
            continue
        row.reconnect_required = True
        sessions = (await session.scalars(select(AgentSession).where(
            AgentSession.user_id == row.user_id, AgentSession.ended_at.is_(None)))).all()
        for item in sessions:
            item.ended_at = item.last_heartbeat_at


# ---- distribution ------------------------------------------------------------------------

async def eligible_agents(session, now: datetime) -> list[str]:
    """Connected agents, next in the rotation first (never-assigned ones go first)."""
    rows = (await session.scalars(select(AgentPresence).where(
        AgentPresence.role == AGENT_ROLE, AgentPresence.status == 'available',
        AgentPresence.last_heartbeat_at >= now - offline_after())
        .order_by(AgentPresence.last_assigned_at.is_not(None), AgentPresence.last_assigned_at,
                  AgentPresence.user_id))).all()
    return [r.user_id for r in rows if is_eligible(r, now)]


async def _move(session, contact: PhoneRegistry, target: str | None, now: datetime,
                action: str) -> bool:
    """Hand a still-`new` contact to `target` (None = back to the pool), only if nobody has
    changed it since it was read."""
    holder = PhoneRegistry.advisor_id.is_(None) if contact.advisor_id is None \
        else PhoneRegistry.advisor_id == contact.advisor_id
    result = await session.execute(update(PhoneRegistry).where(
        PhoneRegistry.id == contact.id, holder, PhoneRegistry.status == 'new')
        .values(advisor_id=target, assigned_at=now if target else None, updated_at=now))
    if result.rowcount != 1:
        return False
    await audit(session, contact.id, SYSTEM_ACTOR, action, contact.advisor_id, target)
    return True


async def distribute(session, contacts: list[PhoneRegistry], now: datetime,
                     action: str) -> int:
    """Round robin over the connected agents. Returns how many contacts were handed out."""
    order = await eligible_agents(session, now)
    if not order or not contacts:
        return 0
    handed, last_turn = 0, {}
    for index, contact in enumerate(contacts):
        target = order[index % len(order)]
        if await _move(session, contact, target, now, action):
            handed += 1
            last_turn[target] = handed
    for user_id, turn in last_turn.items():
        # microseconds keep the order of the turns inside one batch
        await session.execute(update(AgentPresence).where(AgentPresence.user_id == user_id)
                              .values(last_assigned_at=now + timedelta(microseconds=turn)))
    return handed


async def assign_pool(session, now: datetime | None = None) -> int:
    """Contacts nobody has been given yet, oldest first (the hot ones are the waiting ones)."""
    now = now or utcnow()
    pool = (await session.scalars(select(PhoneRegistry).where(
        PhoneRegistry.advisor_id.is_(None), PhoneRegistry.status == 'new')
        .order_by(PhoneRegistry.first_captured_at, PhoneRegistry.id).limit(POOL_BATCH))).all()
    return await distribute(session, list(pool), now, 'auto_assign')


async def redistribute_from(session, user_ids, now: datetime | None = None) -> int:
    """Pending contacts of these agents go to the connected ones (or back to the pool)."""
    now = now or utcnow()
    user_ids = list(user_ids)
    if not user_ids:
        return 0
    pending = (await session.scalars(select(PhoneRegistry).where(
        PhoneRegistry.advisor_id.in_(user_ids), PhoneRegistry.status == 'new')
        .order_by(PhoneRegistry.first_captured_at, PhoneRegistry.id))).all()
    pending = list(pending)
    handed = await distribute(session, pending, now, 'auto_reassign')
    if handed == 0:
        for contact in pending:  # nobody to give them to: back to the pool, still hot
            await _move(session, contact, None, now, 'auto_release')
    return handed


async def unavailable_agents(session, now: datetime) -> list[str]:
    """Agents who must not keep pending contacts: paused, or silent past the grace period."""
    limit = now - offline_after() - timedelta(seconds=settings.redistribute_grace_s)
    rows = (await session.scalars(select(AgentPresence).where(
        AgentPresence.role == AGENT_ROLE))).all()
    return [r.user_id for r in rows
            if r.status == 'paused'
            or (r.idle_since and now >= aware_utc(r.idle_since) + IDLE_DISCONNECT)
            or r.last_heartbeat_at is None
            or aware_utc(r.last_heartbeat_at) < limit]


async def run(factory, now: datetime | None = None) -> dict:
    """One tick of the worker: close dead sessions, move contacts away from people who left,
    hand out whatever is waiting."""
    now = now or utcnow()
    out = {'redistributed': 0, 'assigned': 0}
    async with factory() as session, session.begin():
        await close_stale_sessions(session, now)
        if not settings.auto_assignment:
            return out
        out['redistributed'] = await redistribute_from(
            session, await unavailable_agents(session, now), now)
        out['assigned'] = await assign_pool(session, now)
    return out


# ---- API ---------------------------------------------------------------------------------

class Beat(BaseModel):
    visible: bool = True
    status: Literal['available', 'paused', 'offline'] | None = None


async def _mine(session, who, now) -> dict:
    row = await session.get(AgentPresence, who['user_id'])
    pending = await session.scalar(select(func.count()).select_from(PhoneRegistry).where(
        PhoneRegistry.advisor_id == who['user_id'], PhoneRegistry.status == 'new')) or 0
    current = await session.scalar(select(AgentSession).where(AgentSession.user_id == who['user_id'],
        AgentSession.ended_at.is_(None)).order_by(AgentSession.id.desc()).limit(1))
    return {'session_seconds': current.connected_seconds if current else 0,
            'active_seconds': current.active_seconds if current else 0, 'state': state_of(row, now), 'status': row.status if row else 'available',
            'receives': bool(row and is_eligible(row, now)) and settings.auto_assignment,
            'auto_assignment': settings.auto_assignment, 'pending': pending,
            'heartbeat_seconds': 20, 'idle_disconnect_seconds': 900,
            'reconnect_required': bool(row and row.reconnect_required),
            'idle_since': queries.iso(row.idle_since) if row else None}


@router.post('/heartbeat')
async def beat(body: Beat, who=Depends(worker_scope), session=Depends(get_session)):
    """Called every ~20 s by an open app (people only; service tokens have no presence)."""
    now = utcnow()
    if who.get('kind') != 'user':
        return {'state': 'offline', 'receives': False, 'auto_assignment': settings.auto_assignment}
    came_online = await heartbeat(session, who['user_id'], who['role'], body.visible, now,
                                  body.status)
    if settings.auto_assignment and who['role'] == AGENT_ROLE:
        if body.status in ('paused', 'offline'):
            await redistribute_from(session, [who['user_id']], now)
        elif came_online or body.status == 'available':
            await assign_pool(session, now)  # she is here: what is waiting goes out now
    await session.commit()
    return await _mine(session, who, now)


@router.get('/me')
async def me(who=Depends(worker_scope), session=Depends(get_session)):
    if who.get('kind') != 'user':
        return {'state': 'offline', 'receives': False, 'auto_assignment': settings.auto_assignment}
    return await _mine(session, who, utcnow())


def _day_start() -> datetime:
    local = datetime.now(LIMA).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


@router.get('/team')
async def team(who=Depends(manager_scope), session=Depends(get_session)):
    """Lights, load and time connected of every agent. For supervisors, marketing heads and
    managers; no phones, no comments."""
    now = utcnow()
    roles = (await session.scalars(select(UserRole).where(UserRole.role == AGENT_ROLE))).all()
    presence = {r.user_id: r for r in (await session.scalars(select(AgentPresence).where(
        AgentPresence.role == AGENT_ROLE))).all()}
    ids = {r.user_id for r in roles} | set(presence)
    names = await names_of(session, ids)

    load = {}
    for advisor, status, count in (await session.execute(
            select(PhoneRegistry.advisor_id, PhoneRegistry.status, func.count())
            .where(PhoneRegistry.advisor_id.in_(ids)).group_by(PhoneRegistry.advisor_id,
                                                              PhoneRegistry.status))).all():
        entry = load.setdefault(advisor, {'pending': 0, 'worked': 0})
        entry['pending' if status == 'new' else 'worked'] += count

    async def agg(since):
        rows = (await session.execute(
            select(AgentSession.user_id, func.sum(AgentSession.connected_seconds),
                   func.sum(AgentSession.active_seconds), func.count())
            .where(AgentSession.started_at >= since).group_by(AgentSession.user_id))).all()
        return {u: {'connected_seconds': int(c or 0), 'active_seconds': int(a or 0),
                    'sessions': n} for u, c, a, n in rows}

    today, week = await agg(_day_start()), await agg(now - timedelta(days=7))
    empty = {'connected_seconds': 0, 'active_seconds': 0, 'sessions': 0}
    pool = await session.scalar(select(func.count()).select_from(PhoneRegistry).where(
        PhoneRegistry.advisor_id.is_(None), PhoneRegistry.status == 'new')) or 0
    items = []
    for user_id in ids:
        row = presence.get(user_id)
        state = state_of(row, now)
        entry = load.get(user_id, {'pending': 0, 'worked': 0})
        items.append({
            'id': user_id, 'name': names.get(user_id, user_id), 'state': state,
            'light': {'online': 'green', 'paused': 'amber', 'offline': 'red'}[state],
            'receives': bool(row and is_eligible(row, now)) and settings.auto_assignment,
            'last_seen_at': queries.iso(row.last_heartbeat_at) if row else None,
            'last_assigned_at': queries.iso(row.last_assigned_at) if row else None,
            'pending': entry['pending'], 'worked': entry['worked'],
            'today': today.get(user_id, empty), 'week': week.get(user_id, empty)})
    items.sort(key=lambda i: ({'online': 0, 'paused': 1, 'offline': 2}[i['state']], i['name']))
    return {'items': items, 'pool_waiting': pool, 'auto_assignment': settings.auto_assignment,
            'online': sum(i['state'] == 'online' for i in items), 'generated_at': queries.iso(now)}
