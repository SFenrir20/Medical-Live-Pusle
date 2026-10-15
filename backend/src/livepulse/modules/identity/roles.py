"""Business roles of Medical Social Pulse and what each one may do.

Roles are stored server-side (user_roles, keyed by the Clerk user id). Neither the browser
nor Clerk metadata is trusted for authorization. Edit PERMISSIONS to change what a role can do.
"""
from ...shared.config import settings

ROLES = ('agente_ventas', 'gerente', 'jefe_marketing', 'supervisor')
DEFAULT_ROLE = 'agente_ventas'  # least privilege: own profile only

MARKETING = {'screen:marketing', 'read', 'export'}
# Attention workflow (validated server-side; none of these can write events):
CONTACT_WORK = {'contacts:read', 'contacts:claim', 'contacts:update'}
CONTACT_MANAGE = {*CONTACT_WORK, 'contacts:read_all', 'contacts:assign_any'}
PERMISSIONS: dict[str, set[str]] = {
    # Works own/unassigned contacts; never receives the capture (ingest) token.
    'agente_ventas': {'screen:agent', *CONTACT_WORK},
    'gerente': set(MARKETING),
    'jefe_marketing': set(MARKETING),
    # Both screens plus the operational view, to diagnose failures.
    'supervisor': {'screen:agent', *MARKETING, 'monitor', *CONTACT_MANAGE},
    # Technical owner (ADMIN_USER_IDS): everything, including role management.
    'admin': {'screen:agent', *MARKETING, 'monitor', *CONTACT_MANAGE, 'roles:manage'},
    # Legacy LivePulse mobile roles, kept working.
    'tiktoker': {'screen:agent', *CONTACT_WORK},
    'marketing': {'screen:marketing', 'read'},
    'care': {'screen:agent', *CONTACT_WORK},
}


def role_for(user_id: str, stored: str | None) -> str:
    if user_id in settings.admin_user_ids:
        return 'admin'
    return stored if stored in PERMISSIONS else DEFAULT_ROLE


def screens_for(role: str) -> list[str]:
    allowed = PERMISSIONS.get(role, set())
    return [name.split(':', 1)[1] for name in ('screen:agent', 'screen:marketing')
            if name in allowed]
