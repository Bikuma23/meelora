"""P1.13A — Per-user, per-company module access and sensitive permissions.

Two collections:

* ``user_module_access`` — a user's functional access level (none/read/
  contribute/manage) for a module, scoped by company. A user may have different
  levels per company.
* ``user_permissions`` — explicit sensitive-permission grants, scoped by company.

Key rules enforced here:
* A module access level may NOT be assigned unless the workspace is entitled to
  the module (Client Admin cannot grant an unpurchased module).
* Granting a sensitive permission requires the workspace to be entitled to the
  owning module. ``manage`` never implies any sensitive permission.
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from .entitlements import is_module_entitled
from .modules import MODULE_CODES, is_valid_level, is_valid_module
from .permissions_catalog import is_valid_permission, module_for_permission

_now = lambda: datetime.now(timezone.utc).isoformat()


# ---- Module access ---------------------------------------------------------
async def get_user_module_level(db, workspace_id: str, company_id: str, user_id: str,
                                module_code: str) -> str:
    row = await db.user_module_access.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "module_code": module_code})
    return (row or {}).get("access_level", "none")


async def list_user_module_access(db, workspace_id: str, company_id: str, user_id: str) -> list[dict]:
    rows = await db.user_module_access.find(
        {"workspace_id": workspace_id, "company_id": company_id, "user_id": user_id}).to_list(None)
    by_code = {r.get("module_code"): r.get("access_level", "none") for r in rows}
    return [{"module_code": code, "access_level": by_code.get(code, "none")}
            for code in sorted(MODULE_CODES)]


async def set_user_module_access(db, workspace_id: str, company_id: str, user_id: str,
                                 module_code: str, access_level: str, actor_id: str) -> dict:
    if not is_valid_module(module_code):
        raise HTTPException(status_code=422, detail=f"Module inconnu: {module_code}")
    if not is_valid_level(access_level):
        raise HTTPException(status_code=422, detail=f"Niveau d'accès invalide: {access_level}")
    if access_level != "none" and not await is_module_entitled(db, workspace_id, module_code):
        raise HTTPException(status_code=409,
                            detail=f"Module non souscrit pour ce workspace: {module_code}")
    now = _now()
    existing = await db.user_module_access.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "module_code": module_code})
    changes = {"access_level": access_level, "updated_at": now, "updated_by": actor_id}
    if existing:
        await db.user_module_access.update_one({"_id": existing["_id"]}, {"$set": changes})
    else:
        await db.user_module_access.insert_one(
            {"_id": f"uma_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
             "user_id": user_id, "module_code": module_code, "created_at": now,
             "created_by": actor_id, **changes})
    return {"module_code": module_code, "access_level": access_level}


# ---- Sensitive permissions -------------------------------------------------
async def has_user_permission(db, workspace_id: str, company_id: str, user_id: str,
                              permission_code: str) -> bool:
    row = await db.user_permissions.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "permission_code": permission_code, "granted": True})
    return bool(row)


async def list_user_permissions(db, workspace_id: str, company_id: str, user_id: str) -> list[str]:
    rows = await db.user_permissions.find(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "granted": True}).to_list(None)
    return sorted(r.get("permission_code") for r in rows if r.get("permission_code"))


async def set_user_permission(db, workspace_id: str, company_id: str, user_id: str,
                              permission_code: str, granted: bool, actor_id: str) -> dict:
    if not is_valid_permission(permission_code):
        raise HTTPException(status_code=422, detail=f"Permission inconnue: {permission_code}")
    module_code = module_for_permission(permission_code)
    if granted and not await is_module_entitled(db, workspace_id, module_code):
        raise HTTPException(status_code=409,
                            detail=f"Module non souscrit pour ce workspace: {module_code}")
    now = _now()
    existing = await db.user_permissions.find_one(
        {"workspace_id": workspace_id, "company_id": company_id,
         "user_id": user_id, "permission_code": permission_code})
    changes = {"granted": bool(granted), "updated_at": now, "updated_by": actor_id}
    if existing:
        await db.user_permissions.update_one({"_id": existing["_id"]}, {"$set": changes})
    else:
        await db.user_permissions.insert_one(
            {"_id": f"uperm_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
             "user_id": user_id, "permission_code": permission_code, "module_code": module_code,
             "created_at": now, "created_by": actor_id, **changes})
    return {"permission_code": permission_code, "granted": bool(granted)}


async def ensure_indexes(db) -> None:
    await db.user_module_access.create_index(
        [("workspace_id", 1), ("company_id", 1), ("user_id", 1), ("module_code", 1)],
        unique=True, name="uniq_user_module_access")
    await db.user_module_access.create_index([("user_id", 1)], name="idx_uma_user")
    await db.user_permissions.create_index(
        [("workspace_id", 1), ("company_id", 1), ("user_id", 1), ("permission_code", 1)],
        unique=True, name="uniq_user_permission")
    await db.user_permissions.create_index([("user_id", 1)], name="idx_uperm_user")
