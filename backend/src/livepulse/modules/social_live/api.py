"""Two routers over the same database:
- /api/social-live/*  written by Medical Social Live (scope: ingest)
- /api/marketing/tiktok/*  read by Medical 360 (scope: read; comment export needs: export)
Neither frontend talks to the other; both go through this API."""
from datetime import date, datetime, timedelta
from typing import Literal, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError

from ...shared.db import get_session
from . import queries, service
from .export import build_xlsx
from .models import TiktokAccount, Tiktoker
from .schemas import (
    AccountIn,
    CommentIn,
    EventBatch,
    EventIn,
    FinishIn,
    LiveIn,
    PhoneIn,
    PhoneStatus,
    PhoneUpdate,
    TiktokerIn,
    aware,
)
from .security import require_scope

social = APIRouter(prefix='/api/social-live', tags=['social-live'],
                   dependencies=[Depends(require_scope('ingest'))])
marketing = APIRouter(prefix='/api/marketing/tiktok', tags=['marketing-tiktok'],
                      dependencies=[Depends(require_scope('read'))])


def _day_start(value):
    """date -> start of that day in Lima, as UTC; datetimes are normalized (naive = Lima)."""
    if isinstance(value, datetime):
        return aware(value)
    return aware(datetime(value.year, value.month, value.day))


def period(date_from: date | datetime | None, date_to: date | datetime | None):
    start = _day_start(date_from) if date_from else None
    if date_to is None:
        return start, None
    end = _day_start(date_to)
    # A plain date means "through the end of that day".
    return start, end + timedelta(days=1) if not isinstance(date_to, datetime) else end


async def _live(session, live_id):
    return await service.require_live(session, live_id)


# ---------- ingestion (Medical Social Live) ----------

@social.post('/accounts', status_code=200)
async def upsert_account(body: AccountIn, session=Depends(get_session)):
    async with session.begin():
        row = await session.get(TiktokAccount, body.id)
        try:
            if row is None:
                row = TiktokAccount(**body.model_dump())
                session.add(row)
            else:
                for key, value in body.model_dump().items():
                    setattr(row, key, value)
            await session.flush()
        except IntegrityError:
            raise HTTPException(409, 'Ese usuario de TikTok ya pertenece a otra cuenta.') from None
    return {'id': row.id, 'name': row.name, 'username': row.username, 'type': row.type,
            'active': row.active}


@social.post('/tiktokers', status_code=200)
async def upsert_tiktoker(body: TiktokerIn, session=Depends(get_session)):
    async with session.begin():
        row = await session.get(Tiktoker, body.id)
        if row is None:
            row = Tiktoker(**body.model_dump())
            session.add(row)
        else:
            row.name, row.active = body.name, body.active
    return {'id': row.id, 'name': row.name, 'active': row.active}


@social.post('/lives', status_code=201)
async def create_live(body: LiveIn, response: Response, session=Depends(get_session)):
    async with session.begin():
        live, created = await service.create_live(session, body)
    if not created:
        response.status_code = 200
    return {'id': live.id, 'status': live.status, 'tiktoker_id': live.tiktoker_id,
            'account_id': live.account_id, 'started_at': queries.iso(live.started_at),
            'created': created}


@social.post('/lives/{live_id}/events')
async def add_events(live_id: str, body: Union[EventBatch, EventIn],
                     session=Depends(get_session)):
    events = body.events if isinstance(body, EventBatch) else [body]
    async with session.begin():
        live = await _live(session, live_id)
        results = [await service.ingest(session, live, e) for e in events]
    return {'live_id': live_id, 'received': len(events),
            'accepted': sum(r['accepted'] for r in results),
            'duplicates': sum(r['duplicate'] for r in results), 'results': results}


@social.post('/lives/{live_id}/comments')
async def add_comment(live_id: str, body: CommentIn, session=Depends(get_session)):
    event = EventIn(event_type='comment', username=body.username, text=body.text,
                    timestamp=body.timestamp, event_id=body.event_id)
    async with session.begin():
        live = await _live(session, live_id)
        return await service.ingest(session, live, event)


@social.post('/lives/{live_id}/phones', status_code=201)
async def add_phone(live_id: str, body: PhoneIn, response: Response,
                    session=Depends(get_session)):
    async with session.begin():
        live = await _live(session, live_id)
        row, created = await service.register_phone(session, live, body)
        data = queries.phone_dict(row)
    if not created:
        response.status_code = 200
    return {**data, 'created': created}


@social.patch('/phones/{phone_id}')
async def update_phone(phone_id: int, body: PhoneUpdate, session=Depends(get_session)):
    async with session.begin():
        row = await service.update_phone(session, phone_id, body)
        return queries.phone_dict(row)


@social.patch('/lives/{live_id}/finish')
async def finish(live_id: str, body: FinishIn | None = None, session=Depends(get_session)):
    body = body or FinishIn()
    async with session.begin():
        live = await _live(session, live_id)
        await service.finish_live(session, live, body.ended_at, body.status)
    async with session.begin():
        return await queries.live_detail(session, await _live(session, live_id))


# ---------- queries (Medical 360) ----------

DateParam = Query(default=None, description='YYYY-MM-DD o ISO; sin zona se interpreta en Lima.')


@marketing.get('/overview')
async def overview(date_from: date | datetime | None = DateParam,
                   date_to: date | datetime | None = DateParam,
                   tiktoker_id: str | None = None, account_id: str | None = None,
                   session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.overview(session, date_from=start, date_to=end,
                                  tiktoker_id=tiktoker_id, account_id=account_id)


@marketing.get('/lives')
async def lives(date_from: date | datetime | None = DateParam,
                date_to: date | datetime | None = DateParam,
                tiktoker_id: str | None = None, account_id: str | None = None,
                status: Literal['scheduled', 'live', 'finished', 'cancelled'] | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.list_lives(session, limit, offset, date_from=start, date_to=end,
                                    tiktoker_id=tiktoker_id, account_id=account_id,
                                    status=status)


@marketing.get('/lives/{live_id}')
async def live_detail(live_id: str, session=Depends(get_session)):
    return await queries.live_detail(session, await _live(session, live_id))


@marketing.get('/lives/{live_id}/metrics')
async def live_metrics(live_id: str, session=Depends(get_session)):
    live = await _live(session, live_id)
    detail = await queries.live_detail(session, live)
    return {'live_id': live_id, 'status': live.status, **detail['metrics'],
            'duration_seconds': live.duration_seconds}


@marketing.get('/lives/{live_id}/comments')
async def live_comments(live_id: str, limit: int = Query(100, ge=1, le=500),
                        offset: int = Query(0, ge=0), session=Depends(get_session)):
    return await queries.live_comments(session, await _live(session, live_id), limit, offset)


@marketing.get('/lives/{live_id}/phones')
async def live_phones(live_id: str, status: PhoneStatus | None = None,
                      limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                      session=Depends(get_session)):
    return await queries.live_phones(session, await _live(session, live_id), status,
                                     limit, offset)


@marketing.get('/lives/{live_id}/comments/export',
               dependencies=[Depends(require_scope('export'))])
async def export_comments(live_id: str, session=Depends(get_session)):
    live = await _live(session, live_id)
    if await queries.comments_state(session, live) == 'purged':
        raise queries.retention_error()
    content = await build_xlsx(session, live)
    return Response(content=content, headers={
        'Content-Disposition': f'attachment; filename="comentarios_{live.id}.xlsx"',
        'Cache-Control': 'no-store'},
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@marketing.get('/ranking')
async def ranking(sort_by: Literal['phones', 'leads_per_hour', 'views', 'interested',
                                   'conversion'] = 'phones',
                  date_from: date | datetime | None = DateParam,
                  date_to: date | datetime | None = DateParam,
                  account_id: str | None = None, session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.ranking(session, sort_by, date_from=start, date_to=end,
                                 account_id=account_id)


@marketing.get('/accounts/performance')
async def accounts_performance(date_from: date | datetime | None = DateParam,
                               date_to: date | datetime | None = DateParam,
                               tiktoker_id: str | None = None, session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.accounts_performance(session, date_from=start, date_to=end,
                                              tiktoker_id=tiktoker_id)


@marketing.get('/hourly-performance')
async def hourly_performance(
        granularity: Literal['hour_of_day', 'day', 'week', 'month'] = 'hour_of_day',
        date_from: date | datetime | None = DateParam,
        date_to: date | datetime | None = DateParam,
        tiktoker_id: str | None = None, account_id: str | None = None,
        session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.hourly(session, granularity, start, end, tiktoker_id, account_id)


@marketing.get('/contact-performance')
async def contact_performance(date_from: date | datetime | None = DateParam,
                              date_to: date | datetime | None = DateParam,
                              tiktoker_id: str | None = None, account_id: str | None = None,
                              session=Depends(get_session)):
    start, end = period(date_from, date_to)
    return await queries.contact_performance(session, start, end, tiktoker_id, account_id)

