"""Branches (sedes), the advisors of each one and who gets the next patient.

A patient booked at a branch enters that branch's funnel. Each branch sees only its own
patients. The advisor is chosen by the hour of the appointment against each advisor's shift
(Lima time); where shifts overlap the one with fewer open patients goes first, preferring whoever
is connected right now. If nobody covers that hour the patient waits, free, for any advisor of
the branch to take it."""
import re
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select

from ...shared.db import get_session
from ..analytics.models import UserRole
from ..chat.models import ChatConversation
from ..chat.service import utcnow
from ..social_live.distribution import is_online
from ..social_live.models import AgentPresence, PhoneRegistry
from ..social_live.security import require_scope
from .appointments import plain
from .models import Pipeline, PipelineCard, PipelineStage, Site, Staff

router = APIRouter(prefix='/api/crm/sites', tags=['crm-sites'])
reader = require_scope('wa:read')
admin = require_scope('sites:manage')
staff_reader = require_scope('crm:manage')
LIMA = timezone(timedelta(hours=-5))
ADVISOR_ROLE = 'asesor'
HHMM = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')

DEFAULT_SITES = [
    ('san_isidro', 'San Isidro', ['San Isidro', 'Lince', 'San Isidro Lince']),
    ('los_olivos', 'Los Olivos', ['Los Olivos']),
    ('sjm', 'SJM', ['SJM', 'San Juan de Miraflores']),
    ('ate', 'Ate', ['Ate', 'Ate Vitarte']),
]
# The funnel of the advisors of a branch. The first stage is where the appointments centre's
# patient arrives; the rest are worked by the advisor.
ADVISOR_STAGES = [('Cita agendada', '#6366f1'), ('Asistió', '#14b8a6'), ('Cotizado', '#f59e0b'),
                  ('Separado', '#7c3aed'), ('Operado', '#22c55e')]


def minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:])


def covers(staff: Staff, at: time) -> bool:
    return minutes(staff.shift_start) <= at.hour * 60 + at.minute < minutes(staff.shift_end)


# ---- sites and their funnels -----------------------------------------------------------------

async def site_funnel(session, site: Site) -> Pipeline:
    """The funnel of a branch, created on first use."""
    found = await session.scalar(select(Pipeline).where(Pipeline.site_id == site.id))
    if found is not None:
        return found
    pipeline = Pipeline(name=f'Asesores · {site.name}', site_id=site.id, position=100 + site.id)
    session.add(pipeline)
    await session.flush()
    for index, (name, color) in enumerate(ADVISOR_STAGES):
        session.add(PipelineStage(pipeline_id=pipeline.id, name=name, color=color, position=index))
    await session.flush()
    return pipeline


async def ensure_sites(session) -> list[Site]:
    """The four branches of the clinic, created on first use; the admin edits them afterwards."""
    sites = list((await session.scalars(select(Site).order_by(Site.id))).all())
    if sites:
        return sites
    for key, name, aliases in DEFAULT_SITES:
        session.add(Site(key=key, name=name, aliases=aliases))
    await session.flush()
    sites = list((await session.scalars(select(Site).order_by(Site.id))).all())
    for site in sites:
        await site_funnel(session, site)
    return sites


async def match_site(session, text: str) -> Site | None:
    """The branch an appointment message names ("SJM", "San Isidro / Lince")."""
    wanted = plain(text)
    if not wanted:
        return None
    for site in await ensure_sites(session):
        if not site.active:
            continue
        names = [plain(site.name), *(plain(a) for a in (site.aliases or []))]
        if any(n and (n == wanted or f' {n} ' in f' {wanted} ') for n in names):
            return site
    return None


def my_sites(user_id: str):
    """SQL: the branches this person works at (for the visibility rules)."""
    return select(Staff.site_id).where(Staff.user_id == user_id, Staff.active.is_(True))


def visible_to(me: str, owner):
    """SQL: conversations this person (without the see-all permission) may see: their own, the
    free ones that belong to no branch, and everything of the branch they work at."""
    return or_(and_(owner.is_(None), ChatConversation.site_id.is_(None)), owner == me,
               ChatConversation.site_id.in_(my_sites(me)))


async def site_ids_of(session, user_id: str) -> list[int]:
    return list((await session.scalars(my_sites(user_id))).all())


# ---- who gets the patient --------------------------------------------------------------------

async def choose_advisor(session, site_id: int, start: time | None, now: datetime | None = None):
    """The advisor of the branch whose shift covers the appointment hour (or, without an hour,
    the current one). Overlap: connected first, then the fewest open patients, then the one who
    went longest without a new one. None = nobody covers it: it goes to the branch pool."""
    now = now or utcnow()
    staff = (await session.scalars(select(Staff).join(UserRole, UserRole.user_id == Staff.user_id).where(
        Staff.site_id == site_id, Staff.active.is_(True), UserRole.role == ADVISOR_ROLE))).all()
    at = start or now.astimezone(LIMA).time()
    covering = [s for s in staff if covers(s, at)]
    if not covering:
        return None
    ids = [s.user_id for s in covering]
    presence = {p.user_id: p for p in (await session.scalars(select(AgentPresence).where(
        AgentPresence.user_id.in_(ids)))).all()}

    def connected(user_id: str) -> bool:
        row = presence.get(user_id)
        return bool(row and row.status == 'available' and row.idle_since is None and is_online(row, now))

    pool = [s for s in covering if connected(s.user_id)] or covering
    pipeline = await session.scalar(select(Pipeline).where(Pipeline.site_id == site_id))
    load: dict[str, int] = {}
    if pipeline is not None:
        last = await session.scalar(select(PipelineStage.id).where(
            PipelineStage.pipeline_id == pipeline.id).order_by(PipelineStage.position.desc()).limit(1))
        owner = case((PhoneRegistry.id.is_not(None), PhoneRegistry.advisor_id),
                     else_=ChatConversation.advisor_id)
        rows = await session.execute(
            select(owner, func.count()).select_from(PipelineCard)
            .join(ChatConversation, ChatConversation.id == PipelineCard.conversation_id)
            .outerjoin(PhoneRegistry, PhoneRegistry.phone == ChatConversation.phone)
            .where(PipelineCard.pipeline_id == pipeline.id, PipelineCard.stage_id != last,
                   owner.in_([s.user_id for s in pool])).group_by(owner))
        load = {user_id: count for user_id, count in rows.all()}

    def order(s: Staff):
        row = presence.get(s.user_id)
        went = row.last_assigned_at if row and row.last_assigned_at else datetime.min.replace(tzinfo=timezone.utc)
        return (load.get(s.user_id, 0), went if went.tzinfo else went.replace(tzinfo=timezone.utc), s.user_id)

    chosen = min(pool, key=order)
    row = presence.get(chosen.user_id)
    if row is not None:
        row.last_assigned_at = now
    return chosen.user_id


# ---- API -------------------------------------------------------------------------------------

def site_item(site: Site, pipeline_id: int | None) -> dict:
    return {'id': site.id, 'key': site.key, 'name': site.name, 'aliases': site.aliases or [],
            'active': site.active, 'pipeline_id': pipeline_id}


@router.get('')
async def list_sites(who=Depends(reader), session=Depends(get_session)):
    sites = await ensure_sites(session)
    funnels = {p.site_id: p.id for p in (await session.scalars(
        select(Pipeline).where(Pipeline.site_id.is_not(None)))).all()}
    await session.commit()
    return {'items': [site_item(s, funnels.get(s.id)) for s in sites]}


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    active: bool = True


def clean_aliases(values: list[str]) -> list[str]:
    seen, out = set(), []
    for value in values:
        text = value.strip()[:60]
        if text and plain(text) not in seen:
            seen.add(plain(text))
            out.append(text)
    return out


@router.post('', status_code=201)
async def create_site(body: SiteIn, who=Depends(admin), session=Depends(get_session)):
    await ensure_sites(session)
    key = re.sub(r'[^a-z0-9]+', '_', plain(body.name)).strip('_')[:30] or 'sede'
    if await session.scalar(select(Site.id).where(Site.key == key)):
        raise HTTPException(409, 'Ya existe una sede con ese nombre.')
    site = Site(key=key, name=body.name.strip(), aliases=clean_aliases([body.name, *body.aliases]),
                active=body.active)
    session.add(site)
    await session.flush()
    pipeline = await site_funnel(session, site)
    await session.commit()
    return site_item(site, pipeline.id)


@router.patch('/{site_id}')
async def update_site(site_id: int, body: SiteIn, who=Depends(admin), session=Depends(get_session)):
    site = await session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, 'Sede no encontrada.')
    site.name, site.active = body.name.strip(), body.active
    site.aliases = clean_aliases(body.aliases)
    pipeline = await site_funnel(session, site)
    pipeline.name = f'Asesores · {site.name}'
    pipeline.archived = not site.active
    await session.commit()
    return site_item(site, pipeline.id)


@router.get('/staff')
async def list_staff(who=Depends(staff_reader), session=Depends(get_session)):
    """The advisors (people who signed in with the advisor role) and where they work."""
    people = (await session.scalars(select(UserRole).where(UserRole.role == ADVISOR_ROLE).order_by(
        UserRole.display_name, UserRole.user_id))).all()
    staff = {s.user_id: s for s in (await session.scalars(select(Staff))).all()}
    now = utcnow()
    presence = {p.user_id: p for p in (await session.scalars(select(AgentPresence))).all()}
    out = []
    for person in people:
        s = staff.get(person.user_id)
        row = presence.get(person.user_id)
        out.append({'user_id': person.user_id, 'name': person.display_name or person.user_id,
                    'site_id': s.site_id if s else None,
                    'shift_start': s.shift_start if s else '09:00',
                    'shift_end': s.shift_end if s else '18:00', 'active': s.active if s else False,
                    'online': bool(row and is_online(row, now))})
    return {'items': out}


class StaffIn(BaseModel):
    site_id: int
    shift_start: str = '09:00'
    shift_end: str = '18:00'
    active: bool = True


@router.put('/staff/{user_id}')
async def save_staff(user_id: str, body: StaffIn, who=Depends(admin), session=Depends(get_session)):
    person = await session.get(UserRole, user_id)
    if person is None or person.role != ADVISOR_ROLE:
        raise HTTPException(404, 'Esa persona no tiene el rol de asesor (o aún no inició sesión).')
    if await session.get(Site, body.site_id) is None:
        raise HTTPException(422, 'Sede no válida.')
    if not (HHMM.match(body.shift_start) and HHMM.match(body.shift_end)) or \
            minutes(body.shift_start) >= minutes(body.shift_end):
        raise HTTPException(422, 'El horario debe ser HH:MM y terminar después de empezar.')
    row = await session.get(Staff, user_id)
    if row is None:
        row = Staff(user_id=user_id, site_id=body.site_id)
        session.add(row)
    row.site_id, row.shift_start, row.shift_end, row.active = (
        body.site_id, body.shift_start, body.shift_end, body.active)
    await session.commit()
    return {'user_id': user_id, 'site_id': row.site_id, 'shift_start': row.shift_start,
            'shift_end': row.shift_end, 'active': row.active}


@router.delete('/staff/{user_id}', status_code=204)
async def remove_staff(user_id: str, who=Depends(admin), session=Depends(get_session)):
    row = await session.get(Staff, user_id)
    if row is not None:
        await session.delete(row)
        await session.commit()

