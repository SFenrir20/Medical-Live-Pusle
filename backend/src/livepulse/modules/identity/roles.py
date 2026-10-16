"""What each business role may do. The role itself is assigned in Clerk.

Clerk user Public metadata (editable only from the Clerk dashboard/Backend API, never by the
user):   {"livepulse": {"role": "agente_ventas" | "gerente" | "jefe_marketing" | "supervisor"}}
The role travels inside the signed session token, so it cannot be forged. A person without a
valid role has no access. Edit PERMISSIONS to change what a role can do.
"""
from ...shared.auth import ROLE_CODES
from ...shared.config import settings

ROLES = ROLE_CODES

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
    # Break-glass owner (ADMIN_USER_IDS) in case Clerk metadata is misconfigured.
    'admin': {'screen:agent', *MARKETING, 'monitor', *CONTACT_MANAGE},
}


def role_for(user_id: str, clerk_role: str | None) -> str | None:
    """The effective role, or None = no access."""
    if user_id in settings.admin_user_ids:
        return 'admin'
    return clerk_role if clerk_role in PERMISSIONS else None


def permissions_of(role: str | None) -> set[str]:
    return PERMISSIONS.get(role, set()) if role else set()


def screens_for(role: str | None) -> list[str]:
    allowed = permissions_of(role)
    return [name.split(':', 1)[1] for name in ('screen:agent', 'screen:marketing')
            if name in allowed]
