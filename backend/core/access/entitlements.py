"""P1.13A — Commercial entitlement layer.

Two collections:

* ``workspace_module_entitlements`` — which commercial modules a client
  workspace has received/purchased. Only platform/commercial authority may
  change these; a Client Admin can NEVER grant a module the organization has
  not received.
* ``company_module_enablement`` — optional per-company enablement for
  group/fiduciary environments. Absence means "enabled" (subject to the
  workspace entitlement). A disabling row (``enabled: False``) restricts a
  module for a specific company without losing the workspace entitlement rule.

Effective availability = workspace entitlement AND company enablement (if any)
AND user module access — the user layer lives in ``module_access``.
"""
from datetime import datetime, timezone
from typing import Iterable, Optional
import uuid

from fastapi import HTTPException

from .modules import MODULE_CODES, is_valid_module

ENTITLEMENT_STATUSES = {"active", "inactive", "trial", "suspended"}
_ENTITLED = {"active", "trial"}
_now = lambda: datetime.now(timezone.utc).isoformat()


def public_entitlement(doc: dict) -> dict:
    return {
        "workspace_id": doc.get("workspace_id"),
        "module_code": doc.get("module_code"),
        "status": doc.get("status", "inactive"),
        "activated_at": doc.get("activated_at"),
        "deactivated_at": doc.get("deactivated_at"),
        "source": doc.get("source"),
    }


# ---- Workspace entitlements ------------------------------------------------
async def get_workspace_entitlements(db, workspace_id: str) -> list[dict]:
    rows = await db.workspace_module_entitlements.find({"workspace_id": workspace_id}).to_list(None)
    by_code = {r.get("module_code"): r for r in rows}
    out = []
    for code in sorted(MODULE_CODES):
        row = by_code.get(code)
        out.append(public_entitlement(row) if row else
                   {"workspace_id": workspace_id, "module_code": code, "status": "inactive",
                    "activated_at": None, "deactivated_at": None, "source": None})
    return out


async def is_module_entitled(db, workspace_id: str, module_code: str) -> bool:
    row = await db.workspace_module_entitlements.find_one(
        {"workspace_id": workspace_id, "module_code": module_code})
    return bool(row) and row.get("status") in _ENTITLED


async def set_workspace_entitlement(db, workspace_id: str, module_code: str, status: str,
                                    actor_id: str, source: Optional[str] = None) -> dict:
    if not is_valid_module(module_code):
        raise HTTPException(status_code=422, detail=f"Module inconnu: {module_code}")
    if status not in ENTITLEMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Statut d'entitlement invalide: {status}")
    now = _now()
    existing = await db.workspace_module_entitlements.find_one(
        {"workspace_id": workspace_id, "module_code": module_code})
    changes = {"status": status, "updated_at": now, "updated_by": actor_id}
    if source is not None:
        changes["source"] = source
    if status in _ENTITLED:
        changes["activated_at"] = (existing or {}).get("activated_at") or now
        changes["deactivated_at"] = None
    else:
        changes["deactivated_at"] = now
    if existing:
        await db.workspace_module_entitlements.update_one({"_id": existing["_id"]}, {"$set": changes})
        doc = await db.workspace_module_entitlements.find_one({"_id": existing["_id"]})
    else:
        doc = {"_id": f"wme_{uuid.uuid4().hex}", "workspace_id": workspace_id,
               "module_code": module_code, "source": source, "created_at": now,
               "created_by": actor_id, **changes}
        await db.workspace_module_entitlements.insert_one(doc)
    return public_entitlement(doc)


async def seed_workspace_entitlements(db, workspace_id: str,
                                      modules: Optional[Iterable[str]] = None,
                                      actor_id: str = "system_seed") -> dict:
    """Idempotently ensure the given modules are entitled (status=active) for a
    workspace. Enables AVAILABILITY only — grants no user access whatsoever."""
    modules = list(modules or MODULE_CODES)
    created, existing = [], []
    for code in modules:
        row = await db.workspace_module_entitlements.find_one(
            {"workspace_id": workspace_id, "module_code": code})
        if row and row.get("status") in _ENTITLED:
            existing.append(code)
            continue
        await set_workspace_entitlement(db, workspace_id, code, "active", actor_id, source="seed")
        created.append(code)
    return {"workspace_id": workspace_id, "activated": created, "already_active": existing}


# ---- Company module enablement (optional per-company restriction) ----------
async def get_company_enablement(db, workspace_id: str, company_id: str) -> list[dict]:
    rows = await db.company_module_enablement.find(
        {"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    by_code = {r.get("module_code"): r for r in rows}
    out = []
    for code in sorted(MODULE_CODES):
        row = by_code.get(code)
        # Absence => enabled (governed by the workspace entitlement).
        out.append({"module_code": code,
                    "enabled": bool(row.get("enabled", True)) if row else True,
                    "explicit": bool(row)})
    return out


async def is_module_enabled_for_company(db, workspace_id: str, company_id: str, module_code: str) -> bool:
    row = await db.company_module_enablement.find_one(
        {"workspace_id": workspace_id, "company_id": company_id, "module_code": module_code})
    if not row:
        return True
    return bool(row.get("enabled", True))


async def set_company_enablement(db, workspace_id: str, company_id: str, module_code: str,
                                 enabled: bool, actor_id: str) -> dict:
    if not is_valid_module(module_code):
        raise HTTPException(status_code=422, detail=f"Module inconnu: {module_code}")
    now = _now()
    existing = await db.company_module_enablement.find_one(
        {"workspace_id": workspace_id, "company_id": company_id, "module_code": module_code})
    changes = {"enabled": bool(enabled), "updated_at": now, "updated_by": actor_id}
    if existing:
        await db.company_module_enablement.update_one({"_id": existing["_id"]}, {"$set": changes})
    else:
        await db.company_module_enablement.insert_one(
            {"_id": f"cme_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
             "module_code": module_code, "created_at": now, "created_by": actor_id, **changes})
    return {"module_code": module_code, "enabled": bool(enabled), "explicit": True}


async def ensure_indexes(db) -> None:
    await db.workspace_module_entitlements.create_index(
        [("workspace_id", 1), ("module_code", 1)], unique=True, name="uniq_ws_module_entitlement")
    await db.company_module_enablement.create_index(
        [("workspace_id", 1), ("company_id", 1), ("module_code", 1)], unique=True,
        name="uniq_company_module_enablement")
