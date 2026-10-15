"""Legacy Medical 360 bridge (`/v1/integrations/medical360/{monitor,inbox}`).

Deprecated: kept so existing consumers keep working, but it no longer has its own data. Both
views are adapters over the unified read model (social_live.queries), so they show exactly what
`/api/marketing/tiktok/*` shows: unique contacts by first capture, explicit LIVE responsibility and the
attention state set by the sales team. New consumers should use the /api routes."""
from ..social_live import queries


async def monitor(session):
    data = await queries.monitor(session)
    rows = []
    for item in data['accounts']:
        metrics = item['metrics'] or {}
        rows.append({
            'account_id': item['account_id'], 'account': item['account'],
            'on_air': item['on_air'], 'broadcast_id': item['live_id'],
            'tiktoker_id': None, 'tiktoker': item['tiktoker'],
            'started_at': item['started_at'], 'ended_at': item['ended_at'],
            'end_confirmed': None,
            'peak_viewers': metrics.get('peak_viewers'),
            'average_viewers': metrics.get('average_viewers'),
            'comments': metrics.get('comments_count', 0), 'likes': metrics.get('likes_count', 0),
            'shares': metrics.get('shares_count', 0),
            'observed_followers': metrics.get('new_followers', 0),
            'donors': metrics.get('donations_count', 0),
            'interested': metrics.get('interested_viewers', 0),
            'contacts': item['contacts'], 'contacts_pending': item['contacts_pending'],
            'pending_events': 0})
    return {'generated_at': data['generated_at'], 'accounts': rows}


async def inbox(session, since=None, limit=100, only_with_phone=False, account_id=None):
    data = await queries.inbox(session, since, limit, only_with_phone, account_id)
    items = []
    for item in data['items']:
        items.append({
            'event_id': f"comment:{item['comment_id']}", 'account_id': item['account_id'],
            'account': item['account'], 'origin': item['origin'],
            'broadcast_id': item['live_id'], 'tiktok_user_id': None,
            'tiktok_username': item['tiktok_username'], 'tiktok_nickname': None,
            'tiktoker_id': item['tiktoker_id'], 'tiktoker': item['tiktoker'],
            'comment': item['comment'], 'phones': item['phones'], 'kind': item['kind'],
            'state': item['state'], 'received_at': item['received_at'],
            'contacted_at': item['contacted_at'], 'lead_id': None})
    return {'generated_at': data['generated_at'], 'since': data['since'], 'items': items,
            'direct_messages': None}
