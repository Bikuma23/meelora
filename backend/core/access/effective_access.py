"""P1.13A — Central effective-access resolver (deny-by-default).

This is the ONE place functional access is decided. Routes and future modules
MUST call ``resolve_effective_access`` instead of re-deriving authorization.

Resolution order (fail-closed at every step):

    identity status
    → company belongs to workspace (else cross_workspace / no-leak)
    → active company membership (organizational relationship)
    → workspace module entitlement
    → company module enablement (if any)
    → user module access level
    → sensitive permission (explicit, if requested)
    → consolidation group scope (if requested)

CRITICAL SEPARATIONS enforced here:
* ADMINISTRATOR != FINANCIAL AUTHORITY — being a workspace/company admin grants
  NO functional module access or sensitive permission. Access comes only from
  user_module_access / user_permissions.
* PLATFORM != COMPANY — ``platform_role`` is never consulted; it can never grant
  client/company access.
"""
from typing import Optional

from .entitlements import is_module_enabled_for_company, is_module_entitled
from .module_access import get_user_module_level, has_user_permission
from .modules import CONSOLIDATION, is_valid_module, level_rank, level_satisfies
from .permissions_catalog import is_valid_permission, module_for_permission
from .scopes import has_group_scope


def _identity_active(user: dict) -> bool:
    if (user.get("status") or "active") != "active":
        return False
    identity_status = user.get("identity_status")
    return identity_status in (None, "active")


async def _active_company_membership(db, workspace_id: str, company_id: str, user_id: str):
    m = await db.company_memberships.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "status": "active"})
    if m:
        return m
    # Legacy P1.12 bridge — organizational relationship only, no functional grant.
    return await db.company_access.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "active": True})


async def _company_in_workspace(db, workspace_id: str, company_id: str):
    return await db.companies.find_one(
        {"workspace_id": workspace_id, "id": company_id,
         "active": {"$ne": False}, "status": {"$ne": "inactive"}})


async def resolve_effective_access(
    db,
    user: dict,
    *,
    workspace_id: Optional[str] = None,
    company_id: Optional[str] = None,
    module: Optional[str] = None,
    permission: Optional[str] = None,
    required_level: str = "read",
    group_id: Optional[str] = None,
) -> dict:
    """Resolve whether ``user`` may act. Returns a structured diagnostic dict
    ``{allowed, reason, module, permission, checks}``. Never raises for a
    denial — callers translate ``reason`` (e.g. ``cross_workspace`` -> 404)."""
    result: dict = {"allowed": False, "reason": None, "module": module,
                    "permission": permission, "company_id": company_id, "checks": {}}

    def deny(reason: str) -> dict:
        result["allowed"] = False
        result["reason"] = reason
        return result

    user_id = user.get("id")

    if not _identity_active(user):
        return deny("identity_inactive")
    result["checks"]["identity"] = "active"

    if not workspace_id:
        return deny("no_workspace_context")
    if not company_id:
        return deny("no_company_context")

    company = await _company_in_workspace(db, workspace_id, company_id)
    if not company:
        # Cross-workspace / unknown company — no-leak (404 at route level).
        return deny("cross_workspace")
    result["checks"]["company"] = "in_workspace"

    membership = await _active_company_membership(db, workspace_id, company_id, user_id)
    if not membership:
        return deny("no_company_membership")
    result["checks"]["membership"] = membership.get("membership_type") or "member"

    # Company context established. With no module/permission requested, an active
    # membership is sufficient (company context exists) but business modules stay
    # unavailable until entitlement + module access are present.
    if module is None and permission is None:
        result["allowed"] = True
        result["reason"] = "member"
        return result

    if permission is not None:
        if not is_valid_permission(permission):
            return deny("unknown_permission")
        module = module or module_for_permission(permission)
    if not is_valid_module(module):
        return deny("unknown_module")
    result["module"] = module

    if not await is_module_entitled(db, workspace_id, module):
        return deny("module_not_entitled")
    result["checks"]["entitlement"] = "active"

    if not await is_module_enabled_for_company(db, workspace_id, company_id, module):
        return deny("module_not_enabled_for_company")
    result["checks"]["enablement"] = "enabled"

    level = await get_user_module_level(db, workspace_id, company_id, user_id, module)
    result["checks"]["access_level"] = level

    if permission is not None:
        # Sensitive permission requires SOME functional access to the module AND
        # an explicit grant. ``manage`` alone never implies a sensitive permission.
        if level_rank(level) < level_rank("read"):
            return deny("module_access_insufficient")
        if not await has_user_permission(db, workspace_id, company_id, user_id, permission):
            return deny("permission_not_granted")
        result["checks"]["permission"] = "granted"
    else:
        if not level_satisfies(level, required_level):
            return deny("module_access_insufficient")

    if module == CONSOLIDATION and group_id is not None:
        if not await has_group_scope(db, workspace_id, user_id, group_id):
            return deny("group_not_in_scope")
        result["checks"]["group_scope"] = "in_scope"

    result["allowed"] = True
    result["reason"] = "granted"
    return result
