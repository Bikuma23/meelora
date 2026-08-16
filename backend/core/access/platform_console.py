"""P1.13D.2 — Meelora platform console (service layer).

Read-only aggregation for Meelora platform STAFF (platform_role in
{platform_admin, support}). This context is STRICTLY separated from the
company/financial context:

* Platform staff NEVER gain financial authority here. The console exposes
  governance & oversight data only (clients, admins, module entitlements,
  logs). The single mutating action reachable from the platform context is the
  emergency Client Admin replacement, handled by the existing governed endpoint
  (POST /companies/{cid}/client-admin/replace), which is itself limited to
  platform_admin.
* Logs are kept physically separate: platform-scoped logs live in
  ``platform_logs``; a client's operational (tenant) logs are read only after
  entering that client's context, and platform-classified events are never
  surfaced in the tenant stream. There is no aggregate "all clients" stream.
"""
from typing import Optional

from fastapi import HTTPException

from ..logs import public_log
from ..workspaces import public_workspace
from ..companies import public_company
from .admin_governance import _user_by_id, _identity_view, company_admin_history, list_workspace_users
from .entitlements import get_company_enablement, get_workspace_entitlements
from .log_scope import classify_scope, public_platform_log


def require_platform_staff(user: dict) -> dict:
    """Fail-closed gate for the Meelora platform context."""
    if user.get("platform_role") not in ("platform_admin", "support"):
        raise HTTPException(status_code=403, detail="Réservé au personnel plateforme Meelora")
    return user


async def _companies(db, ws_id: str) -> list[dict]:
    return await db.companies.find({"workspace_id": ws_id}).to_list(None)


async def _load_workspace(db, ws_id: str) -> dict:
    w = await db.workspaces.find_one({"_id": ws_id})
    if not w:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return w


# ---------------------------------------------------------------------------
# Clients (= workspaces / mandates at the platform level)
# ---------------------------------------------------------------------------
async def list_clients(db) -> list[dict]:
    workspaces = await db.workspaces.find({}).to_list(None)
    out = []
    for w in workspaces:
        ws_id = str(w.get("_id"))
        companies = await _companies(db, ws_id)
        users = await db.users.count_documents({"workspace_id": ws_id})
        active_users = await db.users.count_documents(
            {"workspace_id": ws_id, "status": {"$ne": "inactive"}})
        admins = await db.company_memberships.count_documents(
            {"workspace_id": ws_id, "membership_type": "company_user",
             "role": "admin", "status": "active"})
        out.append({
            **public_workspace(w),
            "companies_count": len(companies),
            "users_count": users,
            "active_users_count": active_users,
            "client_admins_count": admins,
        })
    out.sort(key=lambda c: (c.get("name") or "").lower())
    return out


# ---------------------------------------------------------------------------
# Company portfolio (platform view) — the FULL company registry across the
# platform-authorized scope. This is INDEPENDENT of the caller's own
# company_memberships: platform staff oversee the whole Meelora portfolio.
# ---------------------------------------------------------------------------
async def list_platform_companies(db) -> list[dict]:
    docs = await db.companies.find({}).to_list(None)
    ws_names = {str(w.get("_id")): (w.get("name") or "") for w in await db.workspaces.find({}).to_list(None)}
    out = []
    for c in docs:
        pub = public_company(c)
        pub["workspace_name"] = ws_names.get(c.get("workspace_id"), "")
        pub["is_internal"] = c.get("legacy_prefix") == "acct"
        out.append(pub)
    # Internal Meelora company first, then by name.
    out.sort(key=lambda c: (0 if c.get("is_internal") else 1, (c.get("name") or "").lower()))
    return out


# ---------------------------------------------------------------------------
# Users ATTACHED TO ONE COMPANY (P1.12/P1.13). Source of truth = the company's
# own company_memberships (priority), with the legacy company_access bridge only
# during transition. Identity/profile data comes from the global `users`. A user
# is listed ONLY if a membership ties them to THIS company (no cross-company leak).
# ---------------------------------------------------------------------------
async def company_members(db, company_id: str) -> dict:
    company = await db.companies.find_one({"id": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Société introuvable")
    ws_id = company.get("workspace_id")
    order: list[str] = []
    seen: dict[str, dict] = {}
    async for m in db.company_memberships.find({"workspace_id": ws_id, "company_id": company_id}):
        uid = m.get("user_id")
        if uid in seen:
            continue
        seen[uid] = {"membership_type": m.get("membership_type") or "member",
                     "role": m.get("role"), "membership_status": m.get("status") or "active",
                     "source": "company_membership"}
        order.append(uid)
    # Legacy bridge — only for users not already covered by a P1.12 membership.
    async for a in db.company_access.find({"workspace_id": ws_id, "company_id": company_id, "active": True}):
        uid = a.get("user_id")
        if uid in seen:
            continue
        seen[uid] = {"membership_type": "workspace_staff",
                     "role": a.get("access_role") or a.get("role"), "membership_status": "active",
                     "source": "legacy_company_access"}
        order.append(uid)
    users = []
    for uid in order:
        u = await _user_by_id(db, uid)
        if not u:
            continue
        mods = []
        async for g in db.user_module_access.find(
                {"workspace_id": ws_id, "company_id": company_id, "user_id": uid}):
            mods.append({"module_code": g.get("module_code"), "level": g.get("access_level")})
        info = seen[uid]
        users.append({
            "identity": _identity_view(u),
            "membership_type": info["membership_type"],
            "role": info["role"],
            "membership_status": info["membership_status"],
            "source": info["source"],
            "modules": sorted(mods, key=lambda x: x.get("module_code") or ""),
        })
    users.sort(key=lambda x: (x["identity"].get("email") or ""))
    return {"company_id": company_id, "company_name": company.get("name"),
            "workspace_id": ws_id, "status": company.get("status", "active"),
            "is_internal": company.get("legacy_prefix") == "acct", "users": users}


async def platform_summary(db) -> dict:
    clients = await list_clients(db)
    plat_events = await db.platform_logs.count_documents({})
    return {
        "clients_count": len(clients),
        "companies_count": sum(c.get("companies_count", 0) for c in clients),
        "users_count": sum(c.get("users_count", 0) for c in clients),
        "platform_events": plat_events,
        "clients": clients,
    }


# ---------------------------------------------------------------------------
# One client's card
# ---------------------------------------------------------------------------
async def client_overview(db, ws_id: str) -> dict:
    w = await _load_workspace(db, ws_id)
    companies = await _companies(db, ws_id)
    return {
        "workspace": public_workspace(w),
        "companies": [{"id": c.get("id"), "name": c.get("name"),
                       "legacy_prefix": c.get("legacy_prefix"),
                       "status": c.get("status", "active")} for c in companies],
        "entitlements": await get_workspace_entitlements(db, ws_id),
        "users_count": await db.users.count_documents({"workspace_id": ws_id}),
        "client_admins_count": await db.company_memberships.count_documents(
            {"workspace_id": ws_id, "membership_type": "company_user",
             "role": "admin", "status": "active"}),
    }


async def client_administrators(db, ws_id: str) -> dict:
    await _load_workspace(db, ws_id)
    companies = await _companies(db, ws_id)
    out = []
    for c in companies:
        hist = await company_admin_history(db, ws_id, c.get("id"))
        out.append({"company_id": c.get("id"), "company_name": c.get("name"), **hist})
    return {"companies": out}


async def client_users(db, ws_id: str) -> dict:
    await _load_workspace(db, ws_id)
    return {"users": await list_workspace_users(db, ws_id)}


async def client_modules(db, ws_id: str) -> dict:
    await _load_workspace(db, ws_id)
    companies = await _companies(db, ws_id)
    per_company = []
    for c in companies:
        per_company.append({
            "company_id": c.get("id"), "company_name": c.get("name"),
            "enablement": await get_company_enablement(db, ws_id, c.get("id"))})
    return {"entitlements": await get_workspace_entitlements(db, ws_id),
            "companies": per_company}


async def client_tenant_logs(db, ws_id: str, limit: int = 300) -> list[dict]:
    """Tenant (client) operational logs for ONE client, entered via platform
    context. Platform-scoped events are NEVER surfaced here (defense-in-depth)."""
    await _load_workspace(db, ws_id)
    limit = max(1, min(int(limit or 300), 1000))
    docs = await db.logs.find({"workspace_id": ws_id}).sort("timestamp", -1).limit(limit).to_list(limit)
    return [public_log(d) for d in docs
            if classify_scope(d.get("event_type"), d.get("company_id")) != "platform"]


async def client_support(db, ws_id: str) -> dict:
    await _load_workspace(db, ws_id)
    docs = await db.platform_logs.find(
        {"target_workspace_id": ws_id}).sort("timestamp", -1).limit(100).to_list(100)
    admins = await db.workspace_memberships.find(
        {"workspace_id": ws_id, "role": "admin", "status": "active"}).to_list(None)
    contacts = []
    for m in admins:
        u = await _user_by_id(db, m.get("user_id"))
        if u:
            contacts.append({"name": u.get("name", ""), "email": u.get("email", ""),
                             "role": "admin"})
    return {"contacts": contacts,
            "activity": [public_platform_log(d) for d in docs]}
