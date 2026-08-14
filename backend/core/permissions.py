"""Centralized tenant/company authorization helpers for Meelora V2 (P1.3).

P1.3 deliberately does not rewire every legacy acct/qc9434 route yet. These
helpers are the single authorization layer that P1.4+ routes must call instead
of sprinkling ad-hoc ``company_id`` filters throughout the application.
"""
from typing import Iterable, Optional

from fastapi import HTTPException


def _active_company_filter(workspace_id: str, company_id: Optional[str] = None) -> dict:
    query = {
        "workspace_id": workspace_id,
        "active": {"$ne": False},
        "status": {"$ne": "inactive"},
    }
    if company_id is not None:
        query["id"] = company_id
    return query


def require_tenant_context(user: dict) -> str:
    """Return workspace_id or fail closed for users not migrated to a tenant."""
    workspace_id = user.get("workspace_id")
    if not workspace_id or not user.get("tenant_migrated"):
        raise HTTPException(status_code=403, detail="Contexte workspace requis")
    return workspace_id


async def require_same_workspace(db, company_id: str, user: dict) -> dict:
    """Load an active company only inside the authenticated user's workspace.

    A cross-workspace company is returned as 404 to avoid leaking tenant data.
    """
    workspace_id = require_tenant_context(user)
    company = await db.companies.find_one(_active_company_filter(workspace_id, company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Société introuvable")
    return company


async def get_company_access(db, company_id: str, user: dict) -> Optional[dict]:
    """Return an active company grant for a user via the new company_memberships
    model, falling back to the legacy company_access bridge (P1.12 dual-read)."""
    workspace_id = require_tenant_context(user)
    membership = await db.company_memberships.find_one({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "user_id": user.get("id"),
        "status": "active",
    })
    if membership:
        return membership
    return await db.company_access.find_one({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "user_id": user.get("id"),
        "active": True,
    })


def _membership_role(access: dict) -> Optional[str]:
    # company_memberships uses ``role``; legacy company_access uses ``access_role``.
    return access.get("role") if "membership_type" in access else access.get("access_role")


async def require_workspace_admin(db, user: dict) -> str:
    """Require a workspace admin (via workspace_memberships or legacy role)."""
    workspace_id = require_tenant_context(user)
    if user.get("role") == "admin":
        return workspace_id
    membership = await db.workspace_memberships.find_one({
        "workspace_id": workspace_id, "user_id": user.get("id"), "status": "active", "role": "admin",
    })
    if not membership:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs du workspace")
    return workspace_id


async def require_workspace_membership(db, user: dict) -> str:
    """Require any active membership in the user's workspace (admin bridge kept)."""
    workspace_id = require_tenant_context(user)
    if user.get("role") == "admin":
        return workspace_id
    membership = await db.workspace_memberships.find_one({
        "workspace_id": workspace_id, "user_id": user.get("id"), "status": "active",
    })
    if not membership:
        raise HTTPException(status_code=403, detail="Aucune appartenance active à ce workspace")
    return workspace_id


async def require_company_local_admin(db, company_id: str, user: dict) -> dict:
    """Authorize company-local user administration: workspace admin OR an active
    company_user membership with role=admin for THIS company only."""
    company = await require_same_workspace(db, company_id, user)
    if user.get("role") == "admin":
        return company
    membership = await db.company_memberships.find_one({
        "workspace_id": company.get("workspace_id"),
        "company_id": company_id,
        "user_id": user.get("id"),
        "membership_type": "company_user",
        "role": "admin",
        "status": "active",
    })
    if not membership:
        raise HTTPException(status_code=403, detail="Accès réservé à l'administrateur de cette société")
    return company


async def require_company_access(
    db,
    company_id: str,
    user: dict,
    allowed_roles: Optional[Iterable[str]] = None,
) -> dict:
    """Authorize a company request and return the company document.

    Admins may access every active company in their own workspace. Other users
    require an active company_membership (or legacy company_access bridge).
    """
    company = await require_same_workspace(db, company_id, user)
    if user.get("role") == "admin":
        return company

    access = await get_company_access(db, company_id, user)
    if not access:
        raise HTTPException(status_code=403, detail="Accès à cette société non autorisé")

    if allowed_roles is not None and _membership_role(access) not in set(allowed_roles):
        raise HTTPException(status_code=403, detail="Niveau d'accès insuffisant")
    return company


async def require_company_admin(db, company_id: str, user: dict) -> dict:
    """Workspace-admin-only company operation (financial structural admin).

    NOTE: company-local admins are intentionally NOT allowed here — they may
    only manage company-local users (see require_company_local_admin).
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return await require_same_workspace(db, company_id, user)


async def list_accessible_company_ids(db, user: dict) -> list[str]:
    """Return company IDs visible to the user in the current workspace.

    Admin visibility from companies; user visibility from the union of
    company_memberships (P1.12) and legacy company_access (bridge)."""
    workspace_id = require_tenant_context(user)
    if user.get("role") == "admin":
        docs = await db.companies.find(_active_company_filter(workspace_id)).to_list(None)
        return [d.get("id") for d in docs if d.get("id")]

    seen, out = set(), []
    memberships = await db.company_memberships.find({
        "workspace_id": workspace_id, "user_id": user.get("id"), "status": "active",
    }).to_list(None)
    legacy = await db.company_access.find({
        "workspace_id": workspace_id, "user_id": user.get("id"), "active": True,
    }).to_list(None)
    for access in list(memberships) + list(legacy):
        cid = access.get("company_id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out
