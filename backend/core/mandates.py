"""Fiduciary mandate domain service for Meelora V2 Foundation (P1.5).

A mandate is the business relationship between a fiduciary workspace and one
company. It mirrors principal/collaborator assignments for workflow/UI, but
``company_access`` remains the single authorization authority.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .permissions import list_accessible_company_ids, require_same_workspace, require_tenant_context

MandateStatus = Literal["active", "inactive"]


class MandateCreate(BaseModel):
    company_id: str = Field(min_length=1)
    mandate_code: str = Field(min_length=1, max_length=80)
    principal_user_id: str = Field(min_length=1)
    collaborator_user_ids: list[str] = Field(default_factory=list)


class MandateUpdate(BaseModel):
    mandate_code: Optional[str] = Field(default=None, min_length=1, max_length=80)
    principal_user_id: Optional[str] = Field(default=None, min_length=1)
    collaborator_user_ids: Optional[list[str]] = None
    status: Optional[MandateStatus] = None


def public_mandate(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "mandate_code": doc.get("mandate_code"),
        "status": doc.get("status", "active"),
        "principal_user_id": doc.get("principal_user_id"),
        "collaborator_user_ids": list(doc.get("collaborator_user_ids") or []),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


async def _require_fiduciary_workspace(db, user: dict) -> dict:
    workspace_id = require_tenant_context(user)
    workspace = await db.workspaces.find_one({"_id": workspace_id, "status": {"$ne": "inactive"}})
    if not workspace:
        raise HTTPException(status_code=403, detail="Workspace introuvable ou inactif")
    if workspace.get("organization_type") != "fiduciary":
        raise HTTPException(status_code=409, detail="Les mandats sont réservés aux workspaces de type fiduciaire")
    return workspace


async def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")


async def _load_workspace_user(db, workspace_id: str, user_id: str) -> dict:
    # Production users use Mongo ObjectId identifiers. Keep the import lazy so
    # the dependency-light Foundation service remains unit-testable in isolation.
    candidates = []
    try:
        from bson import ObjectId
        candidates.append(("_id", ObjectId(user_id)))
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback to a string ``id`` field (used by isolation tests and any
    # non-ObjectId identifiers) so lookups remain schema-agnostic.
    candidates.append(("id", user_id))
    for key, value in candidates:
        doc = await db.users.find_one({
            key: value,
            "workspace_id": workspace_id,
            "status": {"$ne": "inactive"},
        })
        if doc:
            return doc
    raise HTTPException(status_code=422, detail=f"Utilisateur introuvable dans ce workspace: {user_id}")


def _normalize_collaborators(principal_user_id: str, collaborator_user_ids: list[str]) -> list[str]:
    seen = set()
    out = []
    for uid in collaborator_user_ids:
        if not uid or uid == principal_user_id or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


async def _validate_assignments(db, workspace_id: str, principal_user_id: str, collaborator_user_ids: list[str]) -> list[str]:
    collaborators = _normalize_collaborators(principal_user_id, collaborator_user_ids)
    await _load_workspace_user(db, workspace_id, principal_user_id)
    for uid in collaborators:
        await _load_workspace_user(db, workspace_id, uid)
    return collaborators


async def _ensure_mandate_code_unique(db, workspace_id: str, mandate_code: str, exclude_id: Optional[str] = None):
    query = {"workspace_id": workspace_id, "mandate_code": mandate_code, "status": {"$ne": "inactive"}}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    existing = await db.mandates.find_one(query)
    if existing:
        raise HTTPException(status_code=409, detail="Code mandat déjà utilisé dans ce workspace")


async def _sync_company_access(
    db,
    *,
    workspace_id: str,
    company_id: str,
    principal_user_id: str,
    collaborator_user_ids: list[str],
    actor_user_id: str,
):
    """Make company_access reflect mandate assignments."""
    now = datetime.now(timezone.utc).isoformat()
    await db.company_access.update_many(
        {"workspace_id": workspace_id, "company_id": company_id, "active": True},
        {"$set": {"active": False, "updated_at": now, "updated_by": actor_user_id}},
    )
    assignments = [(principal_user_id, "principal")] + [(uid, "collaborator") for uid in collaborator_user_ids]
    for uid, role in assignments:
        await db.company_access.update_one(
            {"workspace_id": workspace_id, "company_id": company_id, "user_id": uid},
            {
                "$set": {
                    "access_role": role,
                    "active": True,
                    "updated_at": now,
                    "updated_by": actor_user_id,
                },
                "$setOnInsert": {
                    "_id": f"cacc_{uuid.uuid4().hex}",
                    "workspace_id": workspace_id,
                    "company_id": company_id,
                    "user_id": uid,
                    "created_at": now,
                    "created_by": actor_user_id,
                },
            },
            upsert=True,
        )


async def list_mandates_for_user(db, user: dict) -> list[dict]:
    await _require_fiduciary_workspace(db, user)
    workspace_id = require_tenant_context(user)
    query = {"workspace_id": workspace_id, "status": {"$ne": "inactive"}}
    if user.get("role") != "admin":
        company_ids = await list_accessible_company_ids(db, user)
        if not company_ids:
            return []
        query["company_id"] = {"$in": company_ids}
    docs = await db.mandates.find(query).to_list(None)
    docs.sort(key=lambda d: ((d.get("mandate_code") or "").casefold(), d.get("_id") or ""))
    return [public_mandate(d) for d in docs]


async def get_mandate_for_user(db, mandate_id: str, user: dict) -> dict:
    await _require_fiduciary_workspace(db, user)
    workspace_id = require_tenant_context(user)
    doc = await db.mandates.find_one({
        "_id": mandate_id,
        "workspace_id": workspace_id,
        "status": {"$ne": "inactive"},
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Mandat introuvable")
    if user.get("role") != "admin":
        accessible = set(await list_accessible_company_ids(db, user))
        if doc.get("company_id") not in accessible:
            raise HTTPException(status_code=404, detail="Mandat introuvable")
    return public_mandate(doc)


async def create_mandate_for_admin(db, user: dict, payload: MandateCreate) -> dict:
    await _require_admin(user)
    await _require_fiduciary_workspace(db, user)
    workspace_id = require_tenant_context(user)
    await require_same_workspace(db, payload.company_id, user)
    existing = await db.mandates.find_one({
        "workspace_id": workspace_id,
        "company_id": payload.company_id,
        "status": {"$ne": "inactive"},
    })
    if existing:
        raise HTTPException(status_code=409, detail="Cette société possède déjà un mandat actif")
    code = payload.mandate_code.strip()
    await _ensure_mandate_code_unique(db, workspace_id, code)
    collaborators = await _validate_assignments(db, workspace_id, payload.principal_user_id, payload.collaborator_user_ids)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"mnd_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "company_id": payload.company_id,
        "mandate_code": code,
        "status": "active",
        "principal_user_id": payload.principal_user_id,
        "collaborator_user_ids": collaborators,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
        "updated_by": user.get("id"),
    }
    await _sync_company_access(
        db,
        workspace_id=workspace_id,
        company_id=payload.company_id,
        principal_user_id=payload.principal_user_id,
        collaborator_user_ids=collaborators,
        actor_user_id=user.get("id"),
    )
    await db.mandates.insert_one(doc)
    return public_mandate(doc)


async def update_mandate_for_admin(db, mandate_id: str, user: dict, payload: MandateUpdate) -> dict:
    await _require_admin(user)
    await _require_fiduciary_workspace(db, user)
    workspace_id = require_tenant_context(user)
    current = await db.mandates.find_one({"_id": mandate_id, "workspace_id": workspace_id})
    if not current:
        raise HTTPException(status_code=404, detail="Mandat introuvable")
    await require_same_workspace(db, current.get("company_id"), user)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_mandate(current)
    code = changes.get("mandate_code")
    if code is not None:
        code = code.strip()
        await _ensure_mandate_code_unique(db, workspace_id, code, exclude_id=mandate_id)
        changes["mandate_code"] = code
    principal = changes.get("principal_user_id", current.get("principal_user_id"))
    collaborators = changes.get("collaborator_user_ids", current.get("collaborator_user_ids") or [])
    collaborators = await _validate_assignments(db, workspace_id, principal, collaborators)
    changes["principal_user_id"] = principal
    changes["collaborator_user_ids"] = collaborators
    now = datetime.now(timezone.utc).isoformat()
    changes["updated_at"] = now
    changes["updated_by"] = user.get("id")
    if changes.get("status") == "inactive":
        await db.company_access.update_many(
            {"workspace_id": workspace_id, "company_id": current.get("company_id"), "active": True},
            {"$set": {"active": False, "updated_at": now, "updated_by": user.get("id")}},
        )
    else:
        await _sync_company_access(
            db,
            workspace_id=workspace_id,
            company_id=current.get("company_id"),
            principal_user_id=principal,
            collaborator_user_ids=collaborators,
            actor_user_id=user.get("id"),
        )
    await db.mandates.update_one(
        {"_id": mandate_id, "workspace_id": workspace_id},
        {"$set": changes},
    )
    updated = await db.mandates.find_one({"_id": mandate_id, "workspace_id": workspace_id})
    return public_mandate(updated)
