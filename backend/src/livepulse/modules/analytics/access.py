"""Gates of the legacy /v1 analytics routes. The role is the one assigned in Clerk (see
identity/roles.py); there is no second role table to keep in step."""
from fastapi import Depends, HTTPException

from ...shared.auth import get_current_user
from ...shared.config import settings

# Clerk role -> the legacy section it opens.
LEGACY_SECTION = {'supervisor': 'admin', 'gerente': 'marketing', 'jefe_marketing': 'marketing',
                  'agente_ventas': 'care'}


def role_of(user) -> str | None:
    if user['id'] in settings.admin_user_ids:
        return 'admin'
    return LEGACY_SECTION.get(user.get('role'))


def require_role(*roles):
    async def dependency(user=Depends(get_current_user)):
        role = role_of(user)
        if role is None:
            raise HTTPException(403, 'Tu usuario no tiene un rol asignado en Clerk.')
        if role != 'admin' and role not in roles:
            raise HTTPException(403, 'No tienes permisos para esta sección.')
        return user
    return dependency
