"""Why our figures differ from TikTok Studio, and what we do about what we can control."""
from datetime import datetime, timedelta, timezone

from livepulse.modules.broadcasts.models import Broadcast, RawEvent
from livepulse.modules.social_live.publisher import publish_batch

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, MKT = '/api/social-live', '/api/marketing/tiktok'
T0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)


async def start(client):
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'm', 'username': 'medical.cirugias'})
    r = await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'L', 'account_id': 'medical', 'started_at': (T0 - timedelta(hours=1)).isoformat()})
    assert r.status_code == 201


async def send(client, event_type, seconds, **fields):
    r = await client.post(f'{API}/lives/L/events', headers=INGEST, json={
        'event_type': event_type, 'timestamp': (T0 + timedelta(seconds=seconds)).isoformat(),
        **fields})
    assert r.status_code == 200, r.text


async def metrics(client):
    return (await client.get(f'{MKT}/lives/L/metrics', headers=READ)).json()


async def test_likes_follow_tiktoks_running_total_when_messages_were_missed(env):
    client, _ = env
    await start(client)
    await send(client, 'like', 1, value=10, total=100)      # 90 likes arrived in messages we missed
    await send(client, 'like', 5, value=5, total=120)
    m = await metrics(client)
    assert m['likes_summed'] == 15 and m['likes_reported_total'] == 120
    assert m['likes_count'] == 120                            # the running total fills the gap
    await send(client, 'like', 9, value=3, total=110)         # a stale total never lowers it
    assert (await metrics(client))['likes_reported_total'] == 120
    # Without TikTok's total (older senders) the sum is still what counts.
    await send(client, 'like', 12, value=1000)
    assert (await metrics(client))['likes_count'] == 1018


async def test_average_audience_is_weighted_by_time_not_by_message_count(env):
    client, _ = env
    await start(client)
    await send(client, 'viewer', 0, value=100)
    await send(client, 'viewer', 60, value=200)
    await send(client, 'viewer', 180, value=50)
    await send(client, 'viewer', 600, value=80)      # a long silence: counted for at most 120 s
    m = await metrics(client)
    assert m['peak_viewers'] == 200
    # (100*60 + 200*120 + 50*120) / 300 s; the plain mean of the samples would be 107.5.
    assert m['average_viewers'] == 120.0
    await send(client, 'viewer', 30, value=999)      # arrives late: raises the peak, not the average
    m = await metrics(client)
    assert m['peak_viewers'] == 999 and m['average_viewers'] == 120.0


async def test_visitors_total_reported_by_tiktok_is_kept_next_to_our_own_counts(env):
    client, _ = env
    await start(client)
    await send(client, 'viewer', 0, value=90, total=1500)
    await send(client, 'viewer', 60, value=100, total=2600)
    await send(client, 'view', 61, value=1)
    await send(client, 'viewer', 120, value=95, total=2400)
    m = await metrics(client)
    assert m['visitors_reported_total'] == 2600       # the highest, never the latest
    assert m['views'] == 1                            # our own count of observed entries
    assert m['unique_viewers'] is None                # still not claimed as unique viewers


async def test_monitor_payloads_carry_the_totals_into_the_live(env):
    client, factory = env
    async with factory() as s, s.begin():
        s.add(Broadcast(id=1, account_id='medical', tiktok_username='medical.cirugias',
                        room_id='r', started_at=T0 - timedelta(minutes=5), end_confirmed=False))
        s.add(RawEvent(event_id='medical:r:like:1', account_id='medical', broadcast_id=1,
                       type='like', occurred_at=T0, payload={'count': 7, 'total': 4800}))
        s.add(RawEvent(event_id='medical:r:audience:1', account_id='medical', broadcast_id=1,
                       type='audience', occurred_at=T0,
                       payload={'viewers': 105, 'visitors': 4500}))
    await publish_batch(factory)
    m = (await client.get(f'{MKT}/lives/TT-1/metrics', headers=READ)).json()
    assert m['likes_count'] == 4800 and m['likes_summed'] == 7
    assert m['visitors_reported_total'] == 4500 and m['peak_viewers'] == 105
