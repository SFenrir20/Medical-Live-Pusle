"""Automatic distribution of new contacts among the connected agents, and presence."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.social_live import distribution as dist
from livepulse.modules.social_live import models as m
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings

INGEST = {'Authorization': 'Bearer ingest-secret'}
API = '/api/social-live'
ROLES = {'ana': 'agente_ventas', 'bea': 'agente_ventas', 'cris': 'agente_ventas',
         'dani': 'agente_ventas', 'sup': 'supervisor', 'jefa': 'jefe_marketing'}
T0 = datetime.now(timezone.utc).replace(microsecond=0)
AGENT = 'agente_ventas'


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


def at(seconds):
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': ROLES.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)


@pytest.fixture
async def world(env, people, monkeypatch):
    monkeypatch.setattr(settings, 'auto_assignment', True)
    monkeypatch.setattr(settings, 'presence_offline_after_s', 60)
    monkeypatch.setattr(settings, 'redistribute_grace_s', 60)
    client, factory = env
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'medical', 'username': 'medical.cirugias'})
    r = await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'LIVE', 'account_id': 'medical',
        'started_at': (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()})
    assert r.status_code == 201
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id=u, role=r, display_name=u.title()) for u, r in ROLES.items()])
    return client, factory


class Desk:
    """Drives the scenario: contacts arrive through the API, agents beat at chosen moments."""

    def __init__(self, client, factory):
        self.client, self.factory, self.n = client, factory, 0

    async def lead(self, count=1) -> list[str]:
        phones = []
        for _ in range(count):
            self.n += 1
            phone = f'98{self.n:07d}'
            minutes = 600 - self.n  # strictly increasing capture times
            r = await self.client.post(f'{API}/lives/LIVE/comments', headers=INGEST, json={
                'username': f'user{self.n}', 'text': f'me interesa {phone}',
                'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()})
            assert r.status_code == 200, r.text
            phones.append('+51' + phone)
        return phones

    async def beat(self, user, seconds, visible=True, status=None):
        async with self.factory() as s, s.begin():
            return await dist.heartbeat(s, user, ROLES[user], visible, at(seconds), status)

    async def tick(self, seconds):
        return await dist.run(self.factory, at(seconds))

    async def owners(self, phones=None) -> dict:
        async with self.factory() as s:
            rows = (await s.execute(select(m.PhoneRegistry.phone, m.PhoneRegistry.advisor_id)
                                    .order_by(m.PhoneRegistry.first_captured_at))).all()
        found = {p: a for p, a in rows}
        return {p: found[p] for p in phones} if phones else found

    async def set_status(self, phone, status):
        async with self.factory() as s, s.begin():
            await s.execute(update(m.PhoneRegistry).where(m.PhoneRegistry.phone == phone)
                            .values(status=status))


@pytest.fixture
async def desk(world):
    return Desk(*world)


async def test_contacts_wait_until_someone_connects_then_the_oldest_go_first(desk):
    first, second, third = await desk.lead(3)
    await desk.tick(0)
    assert set((await desk.owners()).values()) == {None}      # nobody is connected
    await desk.beat('ana', 10)
    assert await desk.tick(10) == {'redistributed': 0, 'assigned': 3}
    assert set((await desk.owners()).values()) == {'ana'}


async def test_rotation_follows_agents_joining_and_leaving(desk):
    # agent 1 alone receives everything
    await desk.beat('ana', 0)
    a = await desk.lead(2)
    await desk.tick(1)
    assert set((await desk.owners(a)).values()) == {'ana'}

    # agent 2 joins: from the next contacts on, they alternate (the newcomer goes first)
    await desk.beat('ana', 20)
    await desk.beat('bea', 20)
    b = await desk.lead(4)
    await desk.tick(21)
    assert list((await desk.owners(b)).values()) == ['bea', 'ana', 'bea', 'ana']

    # agent 3 joins: 1, 2, 3 rotation
    for user in ('ana', 'bea', 'cris'):
        await desk.beat(user, 40)
    c = await desk.lead(6)
    await desk.tick(41)
    owners = list((await desk.owners(c)).values())
    assert owners[:3] == ['cris', 'bea', 'ana'] and owners[3:] == owners[:3]

    # agent 1 leaves (silent for longer than the offline wait plus the grace): the rest keep
    # receiving and what she had pending is handed to them
    for user in ('bea', 'cris'):
        await desk.beat(user, 200, status='available')
    d = await desk.lead(2)
    result = await desk.tick(201)
    final = await desk.owners()
    assert 'ana' not in final.values()
    assert result['redistributed'] > 0
    assert set((await desk.owners(d)).values()) == {'bea', 'cris'}

    # agent 4 joins, agent 2 leaves
    for user in ('cris', 'dani'):
        await desk.beat(user, 400, status='available')
    e = await desk.lead(4)
    await desk.tick(401)
    final = await desk.owners()
    assert 'bea' not in final.values()
    assert {final[p] for p in e} == {'cris', 'dani'}
    assert list(final[p] for p in e).count('dani') == 2   # even split between the two


async def test_pending_contacts_wait_out_the_grace_then_move_but_worked_ones_stay(desk):
    await desk.beat('ana', 0)
    phones = await desk.lead(3)
    await desk.tick(1)
    await desk.set_status(phones[0], 'contacted')            # she is already chatting with this one
    await desk.beat('bea', 30)
    # ana went quiet at 0: offline after 60 s, but the grace (60 s) has not run out at 100 s
    await desk.beat('bea', 100, status='available')
    assert (await desk.tick(100))['redistributed'] == 0
    assert set((await desk.owners(phones)).values()) == {'ana'}
    # at 130 s it has: the two untouched ones move to bea; the one being worked stays with ana
    await desk.beat('bea', 130)
    assert (await desk.tick(130))['redistributed'] == 2
    owners = await desk.owners(phones)
    assert owners[phones[0]] == 'ana'
    assert owners[phones[1]] == owners[phones[2]] == 'bea'


async def test_pausing_hands_back_what_is_pending_at_once_and_resuming_receives_again(desk):
    await desk.beat('ana', 0)
    await desk.beat('bea', 0)
    phones = await desk.lead(4)
    await desk.tick(1)
    assert sorted((await desk.owners(phones)).values()) == ['ana', 'ana', 'bea', 'bea']

    await desk.beat('ana', 10, status='paused')              # lunch
    await desk.beat('bea', 10)
    await desk.tick(11)
    assert set((await desk.owners(phones)).values()) == {'bea'}
    extra = await desk.lead(2)
    await desk.tick(12)
    assert set((await desk.owners(extra)).values()) == {'bea'}   # the paused agent gets nothing

    await desk.beat('ana', 30, status='available')
    await desk.beat('bea', 30)
    more = await desk.lead(2)
    await desk.tick(31)
    assert set((await desk.owners(more)).values()) == {'ana', 'bea'}


async def test_when_everybody_leaves_pending_contacts_return_to_the_pool_and_go_out_later(desk):
    await desk.beat('ana', 0)
    phones = await desk.lead(3)
    await desk.tick(1)
    await desk.tick(500)                                     # long silence, nobody online
    assert set((await desk.owners(phones)).values()) == {None}
    await desk.beat('cris', 510)
    await desk.tick(510)
    assert set((await desk.owners(phones)).values()) == {'cris'}


async def test_every_move_is_audited_and_never_done_twice(desk):
    await desk.beat('ana', 0)
    (phone,) = await desk.lead(1)
    await desk.tick(1)
    await desk.tick(2)                                       # nothing left to move
    async with desk.factory() as s:
        rows = (await s.execute(select(m.ContactAudit.actor, m.ContactAudit.action,
                                       m.ContactAudit.value).where(
            m.ContactAudit.actor == dist.SYSTEM_ACTOR))).all()
    assert rows == [(dist.SYSTEM_ACTOR, 'auto_assign', 'ana')]


async def test_sessions_measure_connected_and_active_time(desk):
    for seconds, visible in ((0, True), (20, True), (40, False), (60, True)):
        await desk.beat('ana', seconds, visible)
    async with desk.factory() as s:
        (session,) = (await s.scalars(select(m.AgentSession))).all()
    assert session.connected_seconds == 60
    assert session.active_seconds == 40                      # the 20 s with the tab hidden do not count
    await desk.beat('ana', 400, status='available')                              # came back after a long gap: new session
    await desk.tick(401)
    async with desk.factory() as s:
        rows = (await s.scalars(select(m.AgentSession).order_by(m.AgentSession.id))).all()
    assert len(rows) == 2 and rows[0].ended_at is not None and rows[1].ended_at is None


async def test_agent_sees_only_what_was_given_to_her_and_managers_see_the_team(desk):
    await desk.beat('ana', 0)
    await desk.beat('bea', 0)
    phones = await desk.lead(4)
    await desk.tick(1)
    owners = await desk.owners(phones)
    client = desk.client
    mine = (await client.get('/api/inbox', headers=person('ana'), params={'phone_only': True})).json()
    assert {i['phone'] for i in mine['items']} == {p for p, a in owners.items() if a == 'ana'}
    assert all(i['isMine'] for i in mine['items']) and mine['total'] == 2
    everything = (await client.get('/api/inbox', headers=person('sup'),
                                   params={'phone_only': True})).json()
    assert everything['total'] == 4

    assert (await client.get('/api/presence/team', headers=person('ana'))).status_code == 403
    for who in ('sup', 'jefa'):
        assert (await client.get('/api/presence/team', headers=person(who))).status_code == 200


async def test_heartbeat_endpoint_turns_the_light_on_and_hands_out_the_pool(desk):
    client = desk.client
    phones = await desk.lead(2)
    await desk.tick(0)
    assert set((await desk.owners(phones)).values()) == {None}
    state = (await client.post('/api/presence/heartbeat', headers=person('bea'),
                               json={'visible': True})).json()
    assert state['state'] == 'online' and state['receives'] is True and state['pending'] == 2
    assert set((await desk.owners(phones)).values()) == {'bea'}

    team = (await client.get('/api/presence/team', headers=person('sup'))).json()
    by_id = {i['id']: i for i in team['items']}
    assert by_id['bea']['light'] == 'green' and by_id['bea']['pending'] == 2
    assert by_id['ana']['light'] == 'red' and team['online'] == 1 and team['pool_waiting'] == 0
    assert by_id['bea']['today']['sessions'] == 1

    paused = (await client.post('/api/presence/heartbeat', headers=person('bea'),
                                json={'visible': True, 'status': 'paused'})).json()
    assert paused['state'] == 'paused' and paused['receives'] is False
    team = (await client.get('/api/presence/team', headers=person('sup'))).json()
    assert {i['id']: i['light'] for i in team['items']}['bea'] == 'amber'
    # nobody connected to take them: back to the pool, waiting for the next agent
    assert team['pool_waiting'] == 2


async def test_with_auto_assignment_off_nothing_moves(desk, monkeypatch):
    monkeypatch.setattr(settings, 'auto_assignment', False)
    await desk.beat('ana', 0)
    phones = await desk.lead(2)
    assert await desk.tick(1) == {'redistributed': 0, 'assigned': 0}
    assert set((await desk.owners(phones)).values()) == {None}


async def test_idle_is_yellow_then_latched_red_and_requires_explicit_reconnect(desk):
    await desk.beat('ana', 0)
    await desk.beat('ana', 20, visible=False)
    async with desk.factory() as s:
        row = await s.get(m.AgentPresence, 'ana')
        assert dist.state_of(row, at(20)) == 'paused'
        assert not dist.is_eligible(row, at(20))
    # Heartbeats keep arriving while the tab is hidden; they cannot restart the idle deadline.
    for second in range(40, 921, 20):
        await desk.beat('ana', second, visible=False)
    await desk.beat('ana', 940, visible=True)
    async with desk.factory() as s:
        row = await s.get(m.AgentPresence, 'ana')
        assert dist.state_of(row, at(940)) == 'offline'
        assert row.reconnect_required
        sessions = (await s.scalars(select(m.AgentSession))).all()
        assert len(sessions) == 1 and sessions[0].ended_at is not None
        assert sessions[0].connected_seconds == 920
        assert sessions[0].active_seconds == 20
    await desk.beat('ana', 960, visible=True, status='available')
    async with desk.factory() as s:
        row = await s.get(m.AgentPresence, 'ana')
        assert dist.state_of(row, at(960)) == 'online'
        assert dist.is_eligible(row, at(960))
        assert len((await s.scalars(select(m.AgentSession))).all()) == 2


async def test_activity_before_idle_deadline_recovers_without_new_session(desk):
    await desk.beat('ana', 0)
    await desk.beat('ana', 20, visible=False)
    await desk.beat('ana', 40, visible=True)
    async with desk.factory() as s:
        row = await s.get(m.AgentPresence, 'ana')
        assert dist.state_of(row, at(40)) == 'online'
        assert row.idle_since is None
        assert len((await s.scalars(select(m.AgentSession))).all()) == 1


async def test_silent_or_manually_disconnected_agent_cannot_rejoin_by_passive_beats(desk):
    await desk.beat('ana', 0)
    await desk.tick(100)
    await desk.beat('ana', 110)
    async with desk.factory() as s:
        assert dist.state_of(await s.get(m.AgentPresence, 'ana'), at(110)) == 'offline'
    await desk.beat('ana', 120, status='available')
    await desk.beat('ana', 140, status='offline')
    await desk.beat('ana', 160)
    async with desk.factory() as s:
        assert dist.state_of(await s.get(m.AgentPresence, 'ana'), at(160)) == 'offline'
