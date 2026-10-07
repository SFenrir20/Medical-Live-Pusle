"""Role gates are server-owned. Registration never grants staff privileges."""
from fastapi import Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert

from ...shared.auth import get_current_user
from ...shared.config import settings
from ...shared.db import get_session
from .models import UserRole


async def role_of(session, user):
    if user['id'] in settings.admin_user_ids:
        return 'admin'
    row = await session.get(UserRole, user['id'])
    return row.role if row else 'tiktoker'


def require_role(*roles):
    async def dependency(user=Depends(get_current_user), session=Depends(get_session)):
        role = await role_of(session, user)
        if role != 'admin' and role not in roles:
            raise HTTPException(403, 'No tienes permisos para esta sección.')
        return user
    return dependency


async def register(session, user):
    await session.execute(insert(UserRole).values(user_id=user['id'], role='tiktoker')
                          .on_conflict_do_nothing(index_elements=['user_id']))
    await session.commit()
    return await role_of(session, user)
