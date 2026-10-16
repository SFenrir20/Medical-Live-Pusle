"""In-memory XLSX of a live's detailed comments. Nothing is written to disk."""
import io

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import select

from . import queries
from .models import Live, LiveComment, TiktokAccount
from .schemas import LIMA
from .service import aware_utc

HEADERS = ['fecha', 'hora', 'usuario TikTok', 'comentario', 'teléfono detectado', 'live',
           'TikToker', 'cuenta']
BATCH = 2000


def text_cell(sheet, value):
    """Force a literal string: user-written text must never run as a spreadsheet formula."""
    cell = WriteOnlyCell(sheet, value='' if value is None else str(value))
    cell.data_type = 's'
    return cell


async def build_xlsx(session, live: Live) -> bytes:
    account = await session.get(TiktokAccount, live.account_id)
    # The host is the explicitly assigned LIVE responsible, or unassigned.
    attribution = await queries.load_attribution(session)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Comentarios')
    sheet.append([text_cell(sheet, h) for h in HEADERS])
    last_id = 0
    while True:
        rows = (await session.scalars(select(LiveComment).where(
            LiveComment.live_id == live.id, LiveComment.id > last_id)
            .order_by(LiveComment.id).limit(BATCH))).all()
        if not rows:
            break
        for r in rows:
            local = aware_utc(r.created_at).astimezone(LIMA)
            _, tiktoker = attribution.owner(live.tiktoker_id)
            sheet.append([text_cell(sheet, v) for v in (
                local.strftime('%Y-%m-%d'), local.strftime('%H:%M:%S'), r.username, r.comment,
                r.phone_detected, live.id, tiktoker,
                '@' + account.username if account else '')])
        last_id = rows[-1].id
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


CONTACT_HEADERS = ['teléfono', 'estado', 'asesor', 'fecha primera captura', 'hora primera captura',
                   'cuenta', 'LIVE', 'responsable del LIVE', 'usuario TikTok', 'primer contacto',
                   'minutos hasta el contacto', 'apariciones', 'alertas abiertas']
STATUS_ES = {'new': 'Nuevo', 'contacted': 'Contactado', 'qualified': 'Calificado',
             'discarded': 'Descartado'}


async def build_contacts_xlsx(session, date_from=None, date_to=None, account_id=None,
                              status=None) -> tuple[bytes, int]:
    """One row per CONTACT (a number counts once, at its first capture), with who attended it,
    how many times it reappeared and whether alerts are open: what marketing needs to check
    that a contact was really attended."""
    from sqlalchemy import func

    from ..analytics.models import UserRole
    from .models import CapturedPhone, ContactAlert

    rows = await queries.contact_rows(session, date_from, date_to, account_id)
    if status:
        rows = [(c, live) for c, live in rows if c.status == status]
    attribution = await queries.load_attribution(session)
    accounts = {a.id: a.username for a in (await session.scalars(select(TiktokAccount))).all()}
    appearances = dict((await session.execute(
        select(CapturedPhone.phone, func.count()).group_by(CapturedPhone.phone))).all())
    open_alerts = dict((await session.execute(
        select(ContactAlert.registry_id, func.count()).where(ContactAlert.status == 'open')
        .group_by(ContactAlert.registry_id))).all())
    ids = {c.advisor_id for c, _ in rows if c.advisor_id}
    names = {r.user_id: r.display_name or r.user_id for r in (await session.scalars(
        select(UserRole).where(UserRole.user_id.in_(ids)))).all()} if ids else {}
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Contactos')
    sheet.append([text_cell(sheet, h) for h in CONTACT_HEADERS])
    for contact, live in rows:
        local = aware_utc(contact.first_captured_at).astimezone(LIMA)
        _, host = queries.owner_of(attribution, contact, live)
        minutes = ''
        if contact.contacted_at is not None:
            minutes = str(max(0, int((aware_utc(contact.contacted_at)
                                      - aware_utc(contact.first_captured_at)).total_seconds() // 60)))
        contacted = (aware_utc(contact.contacted_at).astimezone(LIMA).strftime('%Y-%m-%d %H:%M')
                     if contact.contacted_at is not None else '')
        sheet.append([text_cell(sheet, v) for v in (
            contact.phone, STATUS_ES.get(contact.status, contact.status),
            names.get(contact.advisor_id, contact.advisor_id or ''), local.strftime('%Y-%m-%d'),
            local.strftime('%H:%M:%S'),
            '@' + accounts.get(contact.first_account_id, contact.first_account_id or ''),
            contact.first_live_id or '', host, contact.first_username or '', contacted, minutes,
            appearances.get(contact.phone, 0), open_alerts.get(contact.id, 0))])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), len(rows)
