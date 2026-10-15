"""Who am I / who can do what, for Medical Social Pulse (Clerk handles identity)."""
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...shared.auth import get_current_user
from ...shared.config import settings
from ...shared.db import get_session
from ..analytics.models import RoleAudit, UserRole
from .roles import DEFAULT_ROLE, PERMISSIONS, ROLES, role_for, screens_for

router = APIRouter(prefix='/api/auth', tags=['auth'])


async def current_role(session, user_id: str) -> str:
    row = await session.get(UserRole, user_id)
    if row is None and user_id not in settings.admin_user_ids:
        # First sign-in: register with the least-privileged role. A concurrent first call
        # may have won the insert already.
        try:
            async with session.begin_nested():
                session.add(UserRole(user_id=user_id, role=DEFAULT_ROLE))
                await session.flush()
        except IntegrityError:
            pass
        await session.commit()
        row = await session.get(UserRole, user_id)
    return role_for(user_id, row.role if row else None)


@router.get('/me')
async def me(user=Depends(get_current_user), session=Depends(get_session)):
    role = await current_role(session, user['id'])
    permissions = PERMISSIONS[role]
    return {'id': user['id'], 'role': role, 'screens': screens_for(role),
            'permissions': sorted(permissions), 'can_manage_roles': 'roles:manage' in permissions}


async def require_role_manager(user=Depends(get_current_user), session=Depends(get_session)):
    role = await current_role(session, user['id'])
    if 'roles:manage' not in PERMISSIONS[role]:
        raise HTTPException(403, 'Solo el administrador puede gestionar roles.')
    return user


@router.get('/users')
async def users(user=Depends(require_role_manager), session=Depends(get_session)):
    rows = (await session.scalars(select(UserRole).order_by(UserRole.user_id))).all()
    return {'roles': list(ROLES),
            'items': [{'id': r.user_id, 'role': role_for(r.user_id, r.role),
                       'locked': r.user_id in settings.admin_user_ids} for r in rows]}


class RoleBody(BaseModel):
    role: Literal['agente_ventas', 'gerente', 'jefe_marketing', 'supervisor']


@router.put('/users/{user_id}/role')
async def set_role(user_id: str, body: RoleBody, user=Depends(require_role_manager),
                   session=Depends(get_session)):
    if user_id in settings.admin_user_ids or user_id == user['id']:
        raise HTTPException(409, 'No puedes cambiar tu propio rol ni el del administrador.')
    row = await session.get(UserRole, user_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, 'La persona debe iniciar sesión al menos una vez.')
    row.role = body.role
    session.add(RoleAudit(id=str(uuid4()), actor=user['id'], user_id=user_id, role=body.role))
    await session.commit()
    return {'id': user_id, 'role': row.role}
