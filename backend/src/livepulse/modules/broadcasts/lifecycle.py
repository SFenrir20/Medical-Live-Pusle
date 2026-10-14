"""Persistent LIVE lifecycle; all times are observations, not an inferred actual start."""
from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import select, text

from ...shared.config import settings
from ..analytics.models import MonitorState
from ..shifts.service import lock
from .models import Broadcast


class BroadcastStore:
    def __init__(self, factory):
        self.factory = factory

    @asynccontextmanager
    async def lease(self, account):
        # Dedicated connection: the server releases this lock if the process dies.
        async with self.factory.kw['bind'].connect() as session:
            key = 'livepulse-monitor:' + account
            acquired = await session.scalar(text('SELECT pg_try_advisory_lock(hashtext(:key))'),
                                             {'key': key})
            await session.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    await session.execute(text('SELECT pg_advisory_unlock(hashtext(:key))'),
                                          {'key': key})
                    await session.commit()

    async def connected(self, account, room, now):
        if not room:
            raise ValueError('Missing provider room ID')
        async with self.factory() as session, session.begin():
            await lock(session, 'broadcast:' + account)
            active = (await session.scalars(select(Broadcast).where(
                Broadcast.account_id == account, Broadcast.ended_at.is_(None)))).all()
            for row in active:
                if row.room_id != str(room):
                    row.ended_at = now
                    row.end_confirmed = False
            broadcast = await session.scalar(select(Broadcast).where(
                Broadcast.account_id == account, Broadcast.room_id == str(room)))
            if broadcast is None:
                broadcast = Broadcast(account_id=account, room_id=str(room),
                                      tiktok_username=settings.tiktok_accounts[account],
                                      started_at=now, end_confirmed=False)
                session.add(broadcast)
            else:
                # Rejoining the same room corrects a previous offline observation.
                broadcast.ended_at = None
                broadcast.end_confirmed = False
            state = await session.get(MonitorState, account)
            if state is None:
                state = MonitorState(account_id=account)
                session.add(state)
            state.status, state.observed_at = 'live', now
            state.offline_since, state.last_error = None, None
            await session.flush()
            return broadcast.id

    async def touch(self, account, now):
        async with self.factory() as session, session.begin():
            await lock(session, 'broadcast:' + account)
            state = await session.get(MonitorState, account)
            if state:
                state.observed_at = now

    async def observed(self, account, status, now, error=None):
        async with self.factory() as session, session.begin():
            await lock(session, 'broadcast:' + account)
            state = await session.get(MonitorState, account)
            if state is None:
                state = MonitorState(account_id=account, observed_at=now)
                session.add(state)
            state.status, state.observed_at, state.last_error = status, now, error
            if status == 'offline':
                state.offline_since = state.offline_since or now
                if now - state.offline_since >= timedelta(seconds=settings.monitor_end_grace_s):
                    rows = (await session.scalars(select(Broadcast).where(
                        Broadcast.account_id == account, Broadcast.ended_at.is_(None)))).all()
                    for row in rows:
                        row.ended_at = max(row.started_at, state.offline_since)
                        row.end_confirmed = True
            else:
                state.offline_since = None
