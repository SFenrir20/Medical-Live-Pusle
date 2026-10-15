"""In-memory XLSX of a live's detailed comments. Nothing is written to disk."""
import io

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import select

from .models import Live, LiveComment, TiktokAccount, Tiktoker
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
    tiktoker = await session.get(Tiktoker, live.tiktoker_id)
    account = await session.get(TiktokAccount, live.account_id)
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
            sheet.append([text_cell(sheet, v) for v in (
                local.strftime('%Y-%m-%d'), local.strftime('%H:%M:%S'), r.username, r.comment,
                r.phone_detected, live.id, tiktoker.name if tiktoker else '',
                '@' + account.username if account else '')])
        last_id = rows[-1].id
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
