"""Attention workflow on a contact: claim, assign, release, change status.

Rules are enforced here (never in the browser). Every change is an UPDATE conditioned on the
state that was read, so two advisors cannot claim the same contact: the loser gets 409 whatever
the isolation level. Each change writes who/what/when to contact_audit."""
from fastapi import HTTPException
from sqlalchemy import update

from .models import PhoneRegistry
from .service import audit, aware_utc, utcnow

STATUSES = ('new', 'contacted', 'qualified', 'discarded')
CONTACTED = ('contacted', 'qualified')


async def _locked(session, registry_id: int) -> PhoneRegistry:
    row = await session.get(PhoneRegistry, registry_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'Contacto no encontrado.')
    return row


async def _apply(session, row: PhoneRegistry, values: dict):
    """UPDATE ... WHERE id AND advisor/status unchanged since we read them."""
    advisor = PhoneRegistry.advisor_id.is_(None) if row.advisor_id is None \
        else PhoneRegistry.advisor_id == row.advisor_id
    result = await session.execute(update(PhoneRegistry).where(
        PhoneRegistry.id == row.id, advisor, PhoneRegistry.status == row.status)
        .values(**values, updated_at=utcnow()))
    if result.rowcount != 1:
        raise HTTPException(409, 'Otra persona actualizó este contacto. Recarga la lista.')
    await session.refresh(row)


async def claim(session, registry_id: int, actor: str) -> PhoneRegistry:
    row = await _locked(session, registry_id)
    if row.advisor_id == actor:
        return row
    if row.advisor_id is not None:
        raise HTTPException(409, 'Este contacto ya está asignado a otra persona.')
    await _apply(session, row, {'advisor_id': actor, 'assigned_at': utcnow()})
    await audit(session, row.id, actor, 'claim', None, actor)
    return row


async def release(session, registry_id: int, actor: str, *, manager: bool) -> PhoneRegistry:
    row = await _locked(session, registry_id)
    if row.advisor_id is None:
        return row
    if row.advisor_id != actor and not manager:
        raise HTTPException(403, 'Solo puedes liberar tus propios contactos.')
    previous = row.advisor_id
    await _apply(session, row, {'advisor_id': None, 'assigned_at': None})
    await audit(session, row.id, actor, 'release', previous, None)
    return row


async def assign(session, registry_id: int, actor: str, advisor_id: str, *,
                 manager: bool) -> PhoneRegistry:
    if advisor_id == actor:
        return await claim(session, registry_id, actor)
    if not manager:
        raise HTTPException(403, 'Solo un supervisor puede asignar a otra persona.')
    row = await _locked(session, registry_id)
    previous = row.advisor_id
    if previous == advisor_id:
        return row
    await _apply(session, row, {'advisor_id': advisor_id, 'assigned_at': utcnow()})
    await audit(session, row.id, actor, 'assign', previous, advisor_id)
    return row


async def set_status(session, registry_id: int, actor: str, status: str, *,
                     expected_status: str | None = None, manager: bool = False,
                     contacted_at=None) -> PhoneRegistry:
    if status not in STATUSES:
        raise HTTPException(422, 'Estado inválido.')
    row = await _locked(session, registry_id)
    if expected_status is not None and row.status != expected_status:
        raise HTTPException(409, 'Otra persona actualizó este contacto. Recarga la lista.')
    if row.advisor_id not in (None, actor) and not manager:
        raise HTTPException(403, 'Este contacto pertenece a otra persona.')
    if row.status == status and (row.advisor_id is not None or manager):
        return row
    values: dict = {'status': status}
    if row.advisor_id is None:
        values.update(advisor_id=actor, assigned_at=utcnow())  # working a contact claims it
    if status in CONTACTED and row.contacted_at is None:
        # Date of the FIRST contact; later changes never move it.
        moment = aware_utc(contacted_at) if contacted_at else utcnow()
        if moment < aware_utc(row.first_captured_at):
            raise HTTPException(422, 'contacted_at no puede ser anterior a la captura.')
        values['contacted_at'] = moment
    previous = row.status
    await _apply(session, row, values)
    await audit(session, row.id, actor, 'status', previous, status)
    return row
