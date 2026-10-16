"""Who am I and what may I open, for Medical Social Pulse.

Identity AND role come from Clerk (see roles.py). The database only keeps a directory of the
people who signed in (name and last role seen) so supervisors can pick an advisor; it is never
used to decide access."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from ...shared.auth import get_current_user
from ...shared.db import get_session
from ..analytics.models import UserRole
from .roles import permissions_of, role_for, screens_for

router = APIRouter(prefix='/api/auth', tags=['auth'])


async def remember(session, user_id: str, role: str | None, name: str | None = None):
    """Keep the directory in step with Clerk. Best effort: access never depends on it."""
    if role is None:
        return
    row = await session.get(UserRole, user_id)
    if row is None:
        try:
            async with session.begin_nested():
                session.add(UserRole(user_id=user_id, role=role, display_name=name))
                await session.flush()
        except IntegrityError:
            row = await session.get(UserRole, user_id)  # a concurrent first call won
    if row is not None:
        row.role = role
        if name:
            row.display_name = name
    await session.commit()


@router.get('/me')
async def me(user=Depends(get_current_user), session=Depends(get_session)):
    role = role_for(user['id'], user.get('role'))
    permissions = permissions_of(role)
    await remember(session, user['id'], role)
    return {'id': user['id'], 'role': role, 'screens': screens_for(role),
            'permissions': sorted(permissions),
            'reason': None if role else 'Tu usuario no tiene un rol asignado en Clerk.'}


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.put('/me/profile')
async def set_profile(body: ProfileBody, user=Depends(get_current_user),
                      session=Depends(get_session)):
    """Remember the person's display name (shown to supervisors and in the team list)."""
    await remember(session, user['id'], role_for(user['id'], user.get('role')), body.name.strip())
    return {'ok': True}
