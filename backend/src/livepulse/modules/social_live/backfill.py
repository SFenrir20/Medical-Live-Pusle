"""One-off, idempotent conversions used by migration 0006 (and tested on their own).

They insert missing rows and reconcile first capture and attention history without duplicating
contacts. Existing advisors are preserved; attention states keep the furthest recorded progress. Plain SQLAlchemy Core on a synchronous
connection, so the same code runs inside Alembic and in portable tests.

  ensure_lives            broadcasts -> lives (+ account, empty metrics), same ids the live
                          publisher uses (TT-<broadcast id>)
  registry_from_appearances   0005 captured_phones -> one contact per number
  legacy_leads_to_registry    old analytics leads/phones -> contacts (history is kept)
  mark_published          raw events already folded in are not folded in twice
"""
from datetime import datetime, timezone

from sqlalchemy import text

PREFIX = 'TT-'
PROGRESS = {'new': 0, 'discarded': 1, 'contacted': 2, 'qualified': 3}
LEGACY_STATUS = {'new': 'new', 'ready': 'new', 'contacted': 'contacted',
                 'scheduled': 'qualified', 'closed': 'qualified', 'invalid': 'discarded'}


def _now():
    return datetime.now(timezone.utc)


def _moment(value):
    """Rows come back as datetimes (PostgreSQL) or ISO strings (SQLite)."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def ensure_lives(conn) -> int:
    """Create the live (and its account and metrics row) of every broadcast that lacks one."""
    now = _now()
    made = 0
    accounts = {r[0] for r in conn.execute(text('SELECT id FROM tiktok_accounts'))}
    usernames = {r[0] for r in conn.execute(text('SELECT username FROM tiktok_accounts'))}
    existing = {r[0] for r in conn.execute(text('SELECT id FROM lives'))}
    rows = conn.execute(text(
        'SELECT id, account_id, tiktok_username, started_at, ended_at FROM broadcasts '
        'ORDER BY id')).all()
    for bid, account_id, username, started_at, ended_at in rows:
        if account_id not in accounts and username not in usernames:
            conn.execute(text(
                'INSERT INTO tiktok_accounts (id, name, username, type, active, created_at) '
                "VALUES (:id, :name, :username, 'live', :active, :now)"),
                {'id': account_id, 'name': account_id, 'username': username, 'active': True,
                 'now': now})
            accounts.add(account_id)
            usernames.add(username)
        live_id = f'{PREFIX}{bid}'
        if live_id in existing:
            continue
        started, ended = _moment(started_at), _moment(ended_at)
        duration = int((ended - started).total_seconds()) if ended else None
        conn.execute(text(
            'INSERT INTO lives (id, tiktoker_id, account_id, started_at, ended_at, '
            'duration_seconds, status, created_at, updated_at) VALUES '
            '(:id, NULL, :account, :started, :ended, :duration, :status, :now, :now)'),
            {'id': live_id, 'account': account_id, 'started': started, 'ended': ended,
             'duration': duration, 'status': 'finished' if ended else 'live', 'now': now})
        conn.execute(text(
            'INSERT INTO live_metrics (live_id, created_at, updated_at) '
            'VALUES (:id, :now, :now)'), {'id': live_id, 'now': now})
        existing.add(live_id)
        made += 1
    return made


def registry_from_appearances(conn) -> int:
    """Release-0005 data: one row per (live, phone) with its own status. Fold into ONE contact
    per number: earliest appearance is the first capture; the furthest status wins; the first
    contact time is the earliest one recorded."""
    now = _now()
    live_account = {r[0]: r[1] for r in conn.execute(text('SELECT id, account_id FROM lives'))}
    known = {r[0] for r in conn.execute(text('SELECT phone FROM phone_registry'))}
    rows = conn.execute(text(
        'SELECT id, live_id, phone, tiktok_username, source, captured_at, status, advisor_id, '
        'contacted_at FROM captured_phones ORDER BY phone, captured_at, id')).all()
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row[2], []).append(row)
    created = 0
    for phone, items in groups.items():
        first = items[0]
        if phone not in known:
            status = max((i[6] for i in items), key=lambda s: PROGRESS.get(s, 0))
            contacts = [_moment(i[8]) for i in items if i[8] is not None]
            advisor = next((i[7] for i in items if i[7]), None)
            conn.execute(text(
                'INSERT INTO phone_registry (phone, first_live_id, first_account_id, '
                'first_captured_at, first_username, first_source, status, advisor_id, '
                'assigned_at, contacted_at, created_at, updated_at) VALUES (:phone, :live, '
                ':account, :captured, :username, :source, :status, :advisor, :assigned, '
                ':contacted, :now, :now)'),
                {'phone': phone, 'live': first[1], 'account': live_account.get(first[1]),
                 'captured': _moment(first[5]), 'username': first[3], 'source': first[4],
                 'status': status, 'advisor': advisor,
                 'assigned': _moment(first[5]) if advisor else None,
                 'contacted': min(contacts) if contacts else None, 'now': now})
            created += 1
        conn.execute(text('UPDATE captured_phones SET is_new = :new WHERE id = :id'),
                     {'new': True, 'id': first[0]})
        for other in items[1:]:
            conn.execute(text('UPDATE captured_phones SET is_new = :new WHERE id = :id'),
                         {'new': False, 'id': other[0]})
    return created


def refresh_metrics(conn) -> None:
    """phones_captured / phone_mentions follow the appearances (new vs every one)."""
    conn.execute(text(
        'UPDATE live_metrics SET '
        'phones_captured = (SELECT COUNT(*) FROM captured_phones c '
        'WHERE c.live_id = live_metrics.live_id AND c.is_new = :yes), '
        'phone_mentions = (SELECT COUNT(*) FROM captured_phones c '
        'WHERE c.live_id = live_metrics.live_id)'), {'yes': True})


def legacy_leads_to_registry(conn) -> int:
    """Merge legacy capture and attention history, including numbers already converted."""
    now = _now()
    live_ids = {r[0] for r in conn.execute(text('SELECT id FROM lives'))}
    known = {r[0] for r in conn.execute(text('SELECT phone FROM phone_registry'))}
    created = 0
    leads = conn.execute(text(
        'SELECT p.phone, l.id, l.status, l.created_at FROM lead_phones p '
        'JOIN leads l ON l.id = p.lead_id ORDER BY p.phone')).all()
    for phone, lead_id, status, lead_created in leads:
        fact = conn.execute(text(
            'SELECT broadcast_id, account_id, occurred_at, user_key FROM event_facts '
            'WHERE lead_id = :lead ORDER BY occurred_at LIMIT 1'), {'lead': lead_id}).first()
        alias = conn.execute(text(
            'SELECT username, user_key FROM lead_aliases WHERE lead_id = :lead '
            'ORDER BY user_key LIMIT 1'), {'lead': lead_id}).first()
        contacted = conn.execute(text(
            "SELECT MIN(created_at) FROM lead_audit WHERE lead_id = :lead AND action = 'status' "
            "AND value IN ('contacted', 'scheduled', 'closed')"), {'lead': lead_id}).scalar()
        mapped = LEGACY_STATUS.get(status, 'new')
        live_id = f'{PREFIX}{fact[0]}' if fact and f'{PREFIX}{fact[0]}' in live_ids else None
        captured = _moment(fact[2]) if fact else _moment(lead_created)
        contacted_at = _moment(contacted)
        if contacted_at is not None and contacted_at < captured:
            contacted_at = captured
        if phone in known:
            current = conn.execute(text(
                'SELECT * FROM phone_registry WHERE phone = :phone'), {'phone': phone}).one()
            first_at = _moment(current.first_captured_at)
            earlier = captured < first_at
            times = [v for v in (_moment(current.contacted_at), contacted_at) if v is not None]
            merged_status = max((current.status, mapped), key=lambda v: PROGRESS.get(v, 0))
            # Keep the advisor already assigned in the new model. Legacy contacts have
            # no advisor field; a status audit actor is not proof of ownership.
            conn.execute(text(
                'UPDATE phone_registry SET first_live_id = :live, first_account_id = :account, '
                'first_captured_at = :captured, first_username = :username, '
                'first_source = :source, status = :status, contacted_at = :contacted '
                'WHERE phone = :phone'), {
                    'phone': phone,
                    'live': live_id if earlier else current.first_live_id,
                    'account': (fact[1] if fact else None) if earlier else current.first_account_id,
                    'captured': captured if earlier else first_at,
                    'username': ((alias[0] or alias[1]) if alias else None)
                    if earlier else current.first_username,
                    'source': ('comment' if fact else 'manual_capture')
                    if earlier else current.first_source,
                    'status': merged_status, 'contacted': min(times) if times else None})
            continue
        conn.execute(text(
            'INSERT INTO phone_registry (phone, first_live_id, first_account_id, '
            'first_captured_at, first_username, first_source, status, advisor_id, assigned_at, '
            'contacted_at, created_at, updated_at) VALUES (:phone, :live, :account, :captured, '
            ':username, :source, :status, NULL, NULL, :contacted, :now, :now)'),
            {'phone': phone, 'live': live_id, 'account': fact[1] if fact else None,
             'captured': captured, 'username': (alias[0] or alias[1]) if alias else None,
             'source': 'comment' if fact else 'manual_capture', 'status': mapped,
             'contacted': contacted_at, 'now': now})
        known.add(phone)
        created += 1
    return created


def mark_published(conn) -> int:
    """Events whose idempotency key exists were already folded into the read model."""
    result = conn.execute(text(
        'UPDATE raw_events SET published_at = :now WHERE published_at IS NULL AND event_id IN '
        '(SELECT event_id FROM live_event_keys)'), {'now': _now()})
    return result.rowcount or 0


def convert_all(conn) -> dict:
    """Order matters: lives first (FK), then contacts, then the counters."""
    lives = ensure_lives(conn)
    contacts = registry_from_appearances(conn)
    legacy = legacy_leads_to_registry(conn)
    # A legacy capture can precede the first appearance from release 0005. Reconcile
    # the flags against the merged registry so two lives cannot both claim a new number.
    conn.execute(text('UPDATE captured_phones SET is_new = EXISTS ('
                      'SELECT 1 FROM phone_registry r WHERE r.phone = captured_phones.phone '
                      'AND r.first_live_id = captured_phones.live_id)'))
    refresh_metrics(conn)
    return {'lives': lives, 'contacts': contacts, 'legacy_contacts': legacy,
            'published': mark_published(conn)}
