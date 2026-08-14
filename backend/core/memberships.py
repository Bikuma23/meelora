"""P1.12 — Multi-level identity & membership (workspace_memberships, company_memberships).

Separates global identity (users) from workspace membership and company
membership. Authorization keeps the Phase 1 no-leak semantics. company_access
remains readable as a legacy compatibility bridge (dual-read in permissions).
Password hashing / global user creation stays in server.py; these services
operate on already-resolved user_ids.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

MembershipType = Literal["workspace_staff", "company_user"]

ROLE_COMBOS = {
    "workspace_staff": {"principal", "collaborator"},
    "company_user": {"admin", "user"},
}


def validate_combo(membership_type: str, role: str) -> None:
    allowed = ROLE_COMBOS.get(membership_type)
    if allowed is None:
        raise HTTPException(status_code=422, detail=f"membership_type invalide: {membership_type}")
    if role not in allowed:
        raise HTTPException(status_code=422, detail=f"Combinaison invalide: {membership_type} + {role}")


class WorkspaceMemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    name: Optional[str] = Field(default=None, max_length=160)
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)
    role: Literal["admin", "user"] = "user"


class WorkspaceMemberUpdate(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    status: Optional[Literal["active", "inactive"]] = None


class CompanyMemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    name: Optional[str] = Field(default=None, max_length=160)
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)
    membership_type: MembershipType
    role: str


class CompanyMemberUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


def public_workspace_member(m: dict, u: Optional[dict]) -> dict:
    return {
        "id": m.get("_id") or m.get("id"),
        "workspace_id": m.get("workspace_id"),
        "user_id": m.get("user_id"),
        "role": m.get("role"),
        "status": m.get("status", "active"),
        "email": (u or {}).get("email"),
        "name": (u or {}).get("name"),
        "platform_role": (u or {}).get("platform_role"),
    }


def public_company_member(m: dict, u: Optional[dict]) -> dict:
    return {
        "id": m.get("_id") or m.get("id"),
        "workspace_id": m.get("workspace_id"),
        "company_id": m.get("company_id"),
        "user_id": m.get("user_id"),
        "membership_type": m.get("membership_type"),
        "role": m.get("role"),
        "status": m.get("status", "active"),
        "email": (u or {}).get("email"),
        "name": (u or {}).get("name"),
    }


async def _user_by_id(db, user_id: str) -> Optional[dict]:
    try:
        from bson import ObjectId
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if doc:
            return doc
    except Exception:
        pass
    return await db.users.find_one({"_id": user_id}) or await db.users.find_one({"id": user_id})


# ---- Workspace memberships ------------------------------------------------
async def list_workspace_members(db, workspace_id: str) -> list[dict]:
    members = await db.workspace_memberships.find({"workspace_id": workspace_id}).to_list(None)
    out = []
    for m in members:
        out.append(public_workspace_member(m, await _user_by_id(db, m.get("user_id"))))
    out.sort(key=lambda x: (x.get("email") or ""))
    return out


async def upsert_workspace_membership(db, workspace_id: str, user_id: str, role: str, actor_id: str) -> dict:
    existing = await db.workspace_memberships.find_one({"workspace_id": workspace_id, "user_id": user_id})
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.workspace_memberships.update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": role, "status": "active", "updated_at": now, "updated_by": actor_id}},
        )
        doc = await db.workspace_memberships.find_one({"_id": existing["_id"]})
    else:
        doc = {"_id": f"wsm_{uuid.uuid4().hex}", "workspace_id": workspace_id, "user_id": user_id,
               "role": role, "status": "active", "created_at": now, "created_by": actor_id}
        await db.workspace_memberships.insert_one(doc)
    return public_workspace_member(doc, await _user_by_id(db, user_id))


async def update_workspace_membership(db, workspace_id: str, membership_id: str, payload: WorkspaceMemberUpdate, actor_id: str) -> dict:
    m = await db.workspace_memberships.find_one({"_id": membership_id, "workspace_id": workspace_id})
    if not m:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = datetime.now(timezone.utc).isoformat()
        changes["updated_by"] = actor_id
        await db.workspace_memberships.update_one({"_id": membership_id}, {"$set": changes})
        m = await db.workspace_memberships.find_one({"_id": membership_id})
    return public_workspace_member(m, await _user_by_id(db, m.get("user_id")))


# ---- Company memberships --------------------------------------------------
async def list_company_members(db, workspace_id: str, company_id: str, only_company_user: bool = False) -> list[dict]:
    query = {"workspace_id": workspace_id, "company_id": company_id}
    if only_company_user:
        query["membership_type"] = "company_user"
    members = await db.company_memberships.find(query).to_list(None)
    out = []
    for m in members:
        out.append(public_company_member(m, await _user_by_id(db, m.get("user_id"))))
    out.sort(key=lambda x: (x.get("membership_type") or "", x.get("email") or ""))
    return out


async def create_company_membership(db, workspace_id: str, company_id: str, user_id: str,
                                     membership_type: str, role: str, actor_id: str) -> dict:
    validate_combo(membership_type, role)
    existing = await db.company_memberships.find_one({
        "workspace_id": workspace_id, "company_id": company_id, "user_id": user_id,
        "membership_type": membership_type, "status": "active",
    })
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.company_memberships.update_one({"_id": existing["_id"]}, {"$set": {"role": role, "updated_at": now, "updated_by": actor_id}})
        doc = await db.company_memberships.find_one({"_id": existing["_id"]})
    else:
        doc = {"_id": f"cpm_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
               "user_id": user_id, "membership_type": membership_type, "role": role,
               "status": "active", "created_at": now, "created_by": actor_id}
        await db.company_memberships.insert_one(doc)
    return public_company_member(doc, await _user_by_id(db, user_id))


async def update_company_membership(db, workspace_id: str, company_id: str, membership_id: str,
                                    payload: CompanyMemberUpdate, actor_id: str,
                                    restrict_to_company_user: bool = False) -> dict:
    m = await db.company_memberships.find_one({"_id": membership_id, "workspace_id": workspace_id, "company_id": company_id})
    if not m:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    if restrict_to_company_user and m.get("membership_type") != "company_user":
        raise HTTPException(status_code=403, detail="Un admin de société ne peut gérer que les utilisateurs locaux de la société")
    changes = payload.model_dump(exclude_unset=True)
    if "role" in changes:
        validate_combo(m.get("membership_type"), changes["role"])
    if changes:
        changes["updated_at"] = datetime.now(timezone.utc).isoformat()
        changes["updated_by"] = actor_id
        await db.company_memberships.update_one({"_id": membership_id}, {"$set": changes})
        m = await db.company_memberships.find_one({"_id": membership_id})
    return public_company_member(m, await _user_by_id(db, m.get("user_id")))


async def ensure_indexes(db) -> None:
    await db.workspace_memberships.create_index(
        [("workspace_id", 1), ("user_id", 1)], unique=True,
        partialFilterExpression={"status": "active"}, name="uniq_active_workspace_membership")
    await db.workspace_memberships.create_index([("user_id", 1)], name="idx_wsm_user")
    await db.company_memberships.create_index(
        [("workspace_id", 1), ("company_id", 1), ("user_id", 1), ("membership_type", 1)],
        unique=True, partialFilterExpression={"status": "active"}, name="uniq_active_company_membership")
    await db.company_memberships.create_index([("user_id", 1)], name="idx_cpm_user")
    await db.company_memberships.create_index(
        [("workspace_id", 1), ("company_id", 1), ("membership_type", 1)], name="idx_cpm_company_type")
