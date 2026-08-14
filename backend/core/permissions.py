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
    """Return the active access assignment for a standard user, if any."""
    workspace_id = require_tenant_context(user)
    return await db.company_access.find_one({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "user_id": user.get("id"),
        "active": True,
    })


async def require_company_access(
    db,
    company_id: str,
    user: dict,
    allowed_roles: Optional[Iterable[str]] = None,
) -> dict:
    """Authorize a company request and return the company document.

    Admins may access every active company in their own workspace. Standard
    users require an active ``company_access`` row. ``allowed_roles`` can be
    used by future endpoints that require principal-only operations.
    """
    company = await require_same_workspace(db, company_id, user)
    if user.get("role") == "admin":
        return company

    access = await get_company_access(db, company_id, user)
    if not access:
        raise HTTPException(status_code=403, detail="Accès à cette société non autorisé")

    if allowed_roles is not None and access.get("access_role") not in set(allowed_roles):
        raise HTTPException(status_code=403, detail="Niveau d'accès insuffisant")
    return company


async def require_company_admin(db, company_id: str, user: dict) -> dict:
    """Require an admin and ensure the company belongs to the same workspace."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return await require_same_workspace(db, company_id, user)


async def list_accessible_company_ids(db, user: dict) -> list[str]:
    """Return IDs visible to the user inside the current workspace.

    This helper is used by P1.4 to scope company listings. Admin visibility is
    derived from companies; user visibility is derived from company_access.
    """
    workspace_id = require_tenant_context(user)
    if user.get("role") == "admin":
        docs = await db.companies.find(_active_company_filter(workspace_id)).to_list(None)
        return [d.get("id") for d in docs if d.get("id")]

    accesses = await db.company_access.find({
        "workspace_id": workspace_id,
        "user_id": user.get("id"),
        "active": True,
    }).to_list(None)
    seen = set()
    out = []
    for access in accesses:
        company_id = access.get("company_id")
        if company_id and company_id not in seen:
            seen.add(company_id)
            out.append(company_id)
    return out
