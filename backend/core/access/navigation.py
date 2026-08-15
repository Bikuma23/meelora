"""P1.13E — Dynamic company navigation & centralised module authorization.

The sidebar is a pure UX projection of EFFECTIVE ACCESS; it is never derived
from ``user.role``. The security authority is always the backend:

* Business module visible for a normal user =
      workspace entitlement ∩ company enablement ∩ effective user module access.
* CLIENT ADMIN management view (option B.a): a workspace/company admin may SEE
  the subscribed & enabled modules in order to administer them, even without a
  personal business grant — but this NEVER confers business authority. Sensitive
  operations remain gated by explicit ``user_permissions``; the admin overlay
  never grants any sensitive permission.
* PLATFORM != COMPANY — platform_role grants nothing here.

``authorize_module`` is the single helper legacy business routes call (via the
middleware) so that a menu hidden in the UI can never be reached through a
direct URL/API call.
"""
from typing import Optional

from .effective_access import resolve_effective_access
from .entitlements import is_module_enabled_for_company, is_module_entitled
from .modules import ACCOUNTING, BUDGETS, CONSOLIDATION, FIXED_ASSETS, REPORTING, level_rank
from .module_access import has_user_permission
from .permissions_catalog import list_permissions

# Canonical sidebar order for the company context.
NAV_MODULES = [REPORTING, BUDGETS, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION]


def _ctx(user: dict) -> dict:
    return {"id": user.get("id"), "status": user.get("status") or "active",
            "identity_status": user.get("identity_status"),
            "platform_role": user.get("platform_role")}


async def is_company_admin(db, user: dict, workspace_id: str, company_id: str) -> bool:
    """Workspace admin (global) OR company-local admin of THIS company."""
    if user.get("role") == "admin":
        return True
    m = await db.company_memberships.find_one(
        {"workspace_id": workspace_id, "company_id": company_id, "user_id": user.get("id"),
         "membership_type": "company_user", "role": "admin", "status": "active"})
    return bool(m)


async def authorize_module(db, user: dict, workspace_id: str, company_id: str,
                           module: str, required_level: str = "read") -> dict:
    """Central decision for a business module action. Returns
    ``{allowed, reason, source, level}``. Fail-closed. Applies the admin
    management-view overlay for read/write VISIBILITY only — never for sensitive
    permissions (those always route through ``resolve_effective_access``)."""
    res = await resolve_effective_access(
        db, _ctx(user), workspace_id=workspace_id, company_id=company_id,
        module=module, required_level=required_level)
    if res["allowed"]:
        return {"allowed": True, "reason": "user_access", "source": "user_access",
                "level": res["checks"].get("access_level")}
    # No-leak reasons must not be masked by the admin overlay.
    if res["reason"] in ("cross_workspace", "identity_inactive", "no_workspace_context",
                         "no_company_context", "unknown_module"):
        return {"allowed": False, "reason": res["reason"], "source": None, "level": None}
    # Admin management view: entitled + enabled module is visible/administrable.
    if await is_company_admin(db, user, workspace_id, company_id):
        if (await is_module_entitled(db, workspace_id, module)
                and await is_module_enabled_for_company(db, workspace_id, company_id, module)):
            return {"allowed": True, "reason": "admin_view", "source": "admin_view", "level": "manage"}
    return {"allowed": False, "reason": res["reason"], "source": None, "level": None}


async def _user_capabilities(db, workspace_id: str, company_id: str, user_id: str,
                             module: str) -> list[str]:
    """Sensitive permissions the user EXPLICITLY holds for this module (never
    inferred from admin_view or from a ``manage`` level)."""
    out = []
    for p in list_permissions(module):
        if await has_user_permission(db, workspace_id, company_id, user_id, p["code"]):
            out.append(p["code"])
    return out


async def build_company_navigation(db, user: dict, workspace_id: str, company_id: str) -> dict:
    """Return the modules the user may SEE for a company, with effective level,
    source (user_access | admin_view) and explicit sensitive capabilities."""
    admin = await is_company_admin(db, user, workspace_id, company_id)
    modules = []
    for module in NAV_MODULES:
        entitled = await is_module_entitled(db, workspace_id, module)
        enabled = entitled and await is_module_enabled_for_company(db, workspace_id, company_id, module)
        auth = await authorize_module(db, user, workspace_id, company_id, module, "read")
        if not auth["allowed"]:
            continue  # module invisible (not entitled / not enabled / not assigned)
        caps = ([] if auth["source"] == "admin_view"
                else await _user_capabilities(db, workspace_id, company_id, user.get("id"), module))
        modules.append({
            "module_code": module,
            "level": auth["level"] or "read",
            "source": auth["source"],           # user_access | admin_view
            "can_write": (auth["source"] == "admin_view"
                          or level_rank(auth["level"]) >= level_rank("contribute")),
            "capabilities": caps,               # explicit sensitive permissions only
        })
    return {"workspace_id": workspace_id, "company_id": company_id,
            "admin_view": admin, "modules": modules}
