"""Recovery of phones from comments processed before the detector understood disguised numbers."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from livepulse.entrypoints.reprocess_phones import missing_phones, reprocess
from livepulse.entrypoints.worker import process_batch
from livepulse.modules.analytics import processor
from livepulse.modules.analytics.models import EventFact, Lead, LeadAudit, LeadPhone
from livepulse.modules.broadcasts.lifecycle import BroadcastStore
from livepulse.modules.broadcasts.models import RawEvent
from livepulse.shared.db import Base

T = datetime(2026, 10, 14, 15, tzinfo=timezone.utc)


def test_only_numbers_the_fact_does_not_have_yet_are_reported():
    assert missing_phones([], 'Mi cel es 985//857#968 gracias') == ['+51985857968']
    assert missing_phones(['+51985857968'], 'Mi cel es 985//857#968 gracias') == []
    # A second, disguised number is added without touching the one already stored.
    assert missing_phones(['+51912345678'], '912 345 678 y 985//857#968') == ['+51985857968']
    for text_ in ('', None, 'Qué bonito', 'el 12/10/2026 fue genial', 'S/ 1,500.00'):
        assert missing_phones([], text_) == []
    assert missing_phones(None, '985*857*968') == ['+51985857968']


pytestmark_db = pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='PostgreSQL required')


@pytest.fixture
async def factory():
    schema = 'reprocess_' + uuid4().hex
    url = os.environ['DATABASE_URL']
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def _comment(factory, broadcast_id, event_id, user, body):
    async with factory() as s, s.begin():
        s.add(RawEvent(event_id=event_id, account_id='medical', broadcast_id=broadcast_id, type='comment', occurred_at=T,
                       payload={'user': user, 'username': 'u' + user}, raw_text=body))


@pytestmark_db
async def test_reprocess_recovers_disguised_numbers_once_and_never_removes_data(factory, monkeypatch):
    bid = await BroadcastStore(factory).connected('medical', 'room1', T)
    await _comment(factory, bid, 'old', '10', 'Quiero informes, mi cel es 985//857#968')
    await _comment(factory, bid, 'plain', '11', 'Mi número 987 654 321')
    await _comment(factory, bid, 'none', '12', 'Qué bonito, el 12/10/2026')
    # Process them the way production did before the detector improved: disguised numbers were missed.
    real = processor.phones_in
    monkeypatch.setattr(processor, 'phones_in', lambda body, region='PE': [p for p in real(body, region) if '987654321' in p])
    await process_batch(factory)
    monkeypatch.setattr(processor, 'phones_in', real)

    async def snapshot():
        async with factory() as s:
            facts = {f.event_id: f for f in (await s.scalars(select(EventFact))).all()}
            return ({k: list(v.phones) for k, v in facts.items()},
                    {k: v.lead_id for k, v in facts.items()},
                    await s.scalar(select(func.count()).select_from(LeadPhone)))
    phones, leads, phone_rows = await snapshot()
    assert phones['old'] == [] and phones['plain'] == ['+51987654321']

    dry = await reprocess(factory, apply=False)
    assert (dry['scanned'], dry['comments_with_new_phones'], dry['phones_added']) == (3, 1, 1)
    assert await snapshot() == (phones, leads, phone_rows)          # a dry run writes nothing

    done = await reprocess(factory, apply=True)
    assert (done['comments_with_new_phones'], done['phones_added']) == (1, 1)
    phones_after, leads_after, phone_rows_after = await snapshot()
    assert phones_after['old'] == ['+51985857968']
    assert phones_after['plain'] == phones['plain'] and phones_after['none'] == []
    assert leads_after['old'] is not None and leads_after['plain'] == leads['plain']
    assert phone_rows_after == phone_rows + 1
    async with factory() as s:
        assert (await s.scalar(select(LeadPhone.lead_id).where(LeadPhone.phone == '+51985857968'))) == leads_after['old']
        assert await s.get(Lead, leads_after['old']) is not None
        audit = (await s.scalars(select(LeadAudit).where(LeadAudit.action == 'phones'))).all()
        assert len(audit) == 1 and audit[0].actor == 'system:reprocess-phones'
        assert '985' not in (audit[0].note or '')                    # audit never carries the number

    again = await reprocess(factory, apply=True)
    assert again['comments_with_new_phones'] == 0                    # idempotent
    assert await snapshot() == (phones_after, leads_after, phone_rows_after)
