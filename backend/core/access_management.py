"""Admin-facing company assignment service for Meelora V2 Foundation P1.7.

``company_access`` remains the authorization source of truth. When a fiduciary
mandate already exists, its principal/collaborator fields are mirrored from the
resulting access rows so the business representation never drifts from security.
"""
from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from .permissions import require_same_workspace, require_tenant_context

AccessRole = Literal["principal", "collaborator"]


class UserCompanyAssignment(BaseModel):
    company_id: str
    access_role: AccessRole


class UserCompanyAccessUpdate(BaseModel):
    assignments: list[UserCompanyAssignment] = []


async def _workspace_user(db, workspace_id: str, user_id: str) -> dict:
    candidates = []
    try:
        from bson import ObjectId
        candidates.append(("_id", ObjectId(user_id)))
    except Exception:
        pass
    candidates.append(("id", user_id))
    for key, value in candidates:
        doc = await db.users.find_one({key: value, "workspace_id": workspace_id, "status": {"$ne": "inactive"}})
        if doc:
            return doc
    raise HTTPException(status_code=404, detail="Utilisateur introuvable")


async def _require_admin(user: dict) -> str:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return require_tenant_context(user)


async def _sync_existing_mandate(db, workspace_id: str, company_id: str, actor_user_id: str) -> None:
    mandate = await db.mandates.find_one({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "status": {"$ne": "inactive"},
    })
    if not mandate:
        return
    rows = await db.company_access.find({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "active": True,
    }).to_list(None)
    principal = next((r.get("user_id") for r in rows if r.get("access_role") == "principal"), None)
    collaborators = sorted({r.get("user_id") for r in rows if r.get("access_role") == "collaborator" and r.get("user_id")})
    if not principal:
        # Existing mandates are defined to always have a principal. Never mirror
        # an invalid security state into the business object.
        raise HTTPException(status_code=409, detail="Un mandat actif doit conserver un responsable principal")
    now = datetime.now(timezone.utc).isoformat()
    await db.mandates.update_one(
        {"_id": mandate["_id"], "workspace_id": workspace_id},
        {"$set": {
            "principal_user_id": principal,
            "collaborator_user_ids": collaborators,
            "updated_at": now,
            "updated_by": actor_user_id,
        }},
    )


async def list_user_company_access(db, actor: dict, target_user_id: str) -> dict:
    workspace_id = await _require_admin(actor)
    target = await _workspace_user(db, workspace_id, target_user_id)
    companies = await db.companies.find({
        "workspace_id": workspace_id,
        "active": {"$ne": False},
        "status": {"$ne": "inactive"},
    }).to_list(None)
    companies.sort(key=lambda d: ((d.get("name") or d.get("display_name") or "").casefold(), d.get("id") or ""))

    rows = []
    if target.get("role") != "admin":
        rows = await db.company_access.find({
            "workspace_id": workspace_id,
            "user_id": target_user_id,
            "active": True,
        }).to_list(None)
    role_by_company = {r.get("company_id"): r.get("access_role") for r in rows}
    return {
        "user": {
            "id": str(target["_id"]),
            "name": target.get("name", ""),
            "email": target.get("email", ""),
            "role": "user" if target.get("role") == "editor" else target.get("role", "user"),
        },
        "implicit_all": target.get("role") == "admin",
        "companies": [
            {
                "company_id": c.get("id"),
                "name": c.get("name") or c.get("display_name") or c.get("legal_name") or "",
                "company_code": c.get("company_code"),
                "jurisdiction": c.get("jurisdiction"),
                "access_role": "admin" if target.get("role") == "admin" else role_by_company.get(c.get("id")),
            }
            for c in companies
        ],
    }


async def replace_user_company_access(db, actor: dict, target_user_id: str, payload: UserCompanyAccessUpdate) -> dict:
    workspace_id = await _require_admin(actor)
    target = await _workspace_user(db, workspace_id, target_user_id)
    if target.get("role") == "admin":
        raise HTTPException(status_code=409, detail="Les administrateurs ont accès implicitement à toutes les sociétés")

    desired = {}
    for item in payload.assignments:
        if item.company_id in desired:
            raise HTTPException(status_code=422, detail=f"Société dupliquée dans les affectations: {item.company_id}")
        await require_same_workspace(db, item.company_id, actor)
        desired[item.company_id] = item.access_role

    current_rows = await db.company_access.find({
        "workspace_id": workspace_id,
        "user_id": target_user_id,
        "active": True,
    }).to_list(None)
    current = {r.get("company_id"): r for r in current_rows}
    now = datetime.now(timezone.utc).isoformat()
    touched = set(current) | set(desired)

    # Removing/demoting a current principal without naming a replacement in
    # this operation would leave the company ownerless. Require reassignment
    # from another user's access dialog first.
    for company_id, row in current.items():
        if row.get("access_role") == "principal" and desired.get(company_id) != "principal":
            raise HTTPException(
                status_code=409,
                detail="Réattribuez d'abord le responsable principal de cette société à un autre utilisateur",
            )

    # Deactivate removed collaborator assignments for this target.
    for company_id, row in current.items():
        if company_id not in desired:
            await db.company_access.update_one(
                {"_id": row["_id"]},
                {"$set": {"active": False, "updated_at": now, "updated_by": actor.get("id")}},
            )

    for company_id, role in desired.items():
        if role == "collaborator":
            principal = await db.company_access.find_one({
                "workspace_id": workspace_id,
                "company_id": company_id,
                "access_role": "principal",
                "active": True,
            })
            if not principal:
                raise HTTPException(
                    status_code=409,
                    detail="Définissez d'abord un responsable principal pour cette société",
                )
        if role == "principal":
            # Preserve the former principal as collaborator when ownership is
            # reassigned; this avoids accidentally stripping their visibility.
            previous = await db.company_access.find_one({
                "workspace_id": workspace_id,
                "company_id": company_id,
                "access_role": "principal",
                "active": True,
                "user_id": {"$ne": target_user_id},
            })
            if previous:
                await db.company_access.update_one(
                    {"_id": previous["_id"]},
                    {"$set": {"access_role": "collaborator", "updated_at": now, "updated_by": actor.get("id")}},
                )
        await db.company_access.update_one(
            {"workspace_id": workspace_id, "company_id": company_id, "user_id": target_user_id},
            {
                "$set": {
                    "access_role": role,
                    "active": True,
                    "updated_at": now,
                    "updated_by": actor.get("id"),
                },
                "$setOnInsert": {
                    "_id": f"cacc_{uuid.uuid4().hex}",
                    "workspace_id": workspace_id,
                    "company_id": company_id,
                    "user_id": target_user_id,
                    "created_at": now,
                    "created_by": actor.get("id"),
                },
            },
            upsert=True,
        )

    for company_id in touched:
        await _sync_existing_mandate(db, workspace_id, company_id, actor.get("id"))

    return await list_user_company_access(db, actor, target_user_id)
