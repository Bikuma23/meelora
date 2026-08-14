"""Tenant-aware company application service for Meelora V2 Foundation (P1.4)."""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .permissions import (
    list_accessible_company_ids,
    require_company_access,
    require_company_admin,
    require_tenant_context,
)


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=250)
    company_code: Optional[str] = Field(default=None, max_length=80)
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    region: Optional[str] = Field(default=None, max_length=80)
    functional_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[Literal["operating", "holding", "real_estate", "nonprofit", "other"]] = None
    fiscal_year_start: Optional[str] = Field(default=None, max_length=5)


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=250)
    company_code: Optional[str] = Field(default=None, max_length=80)
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    region: Optional[str] = Field(default=None, max_length=80)
    functional_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[Literal["operating", "holding", "real_estate", "nonprofit", "other"]] = None
    fiscal_year_start: Optional[str] = Field(default=None, max_length=5)
    status: Optional[Literal["active", "inactive"]] = None


def public_company(doc: dict) -> dict:
    """Stable company API representation while preserving legacy compatibility."""
    return {
        "id": doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "name": doc.get("name") or doc.get("display_name") or doc.get("legal_name") or "",
        "legal_name": doc.get("legal_name"),
        "display_name": doc.get("display_name") or doc.get("name"),
        "company_code": doc.get("company_code"),
        "jurisdiction": doc.get("jurisdiction"),
        "region": doc.get("region"),
        "functional_currency": doc.get("functional_currency"),
        "industry": doc.get("industry"),
        "company_type": doc.get("company_type"),
        "fiscal_year_start": doc.get("fiscal_year_start"),
        "status": doc.get("status", "active" if doc.get("active", True) else "inactive"),
        "active": doc.get("active", doc.get("status") != "inactive"),
        # Temporary compatibility bridge; removed with Financial Core migration.
        "legacy_prefix": doc.get("legacy_prefix"),
    }


async def list_companies_for_user(db, user: dict) -> list[dict]:
    workspace_id = require_tenant_context(user)
    accessible_ids = await list_accessible_company_ids(db, user)
    if not accessible_ids:
        return []
    docs = await db.companies.find({
        "workspace_id": workspace_id,
        "id": {"$in": accessible_ids},
        "active": {"$ne": False},
        "status": {"$ne": "inactive"},
    }).to_list(None)
    docs.sort(key=lambda d: ((d.get("name") or d.get("display_name") or "").casefold(), d.get("id") or ""))
    return [public_company(d) for d in docs]


async def get_company_for_user(db, company_id: str, user: dict, admin_required: bool = False) -> dict:
    if admin_required:
        doc = await require_company_admin(db, company_id, user)
    else:
        doc = await require_company_access(db, company_id, user)
    return public_company(doc)


async def _ensure_company_code_unique(db, workspace_id: str, company_code: Optional[str], exclude_id: Optional[str] = None):
    if not company_code:
        return
    query = {"workspace_id": workspace_id, "company_code": company_code}
    if exclude_id:
        query["id"] = {"$ne": exclude_id}
    existing = await db.companies.find_one(query)
    if existing:
        raise HTTPException(status_code=409, detail="Code société déjà utilisé dans ce workspace")


async def create_company_for_admin(db, user: dict, payload: CompanyCreate) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    workspace_id = require_tenant_context(user)
    data = payload.model_dump()
    await _ensure_company_code_unique(db, workspace_id, data.get("company_code"))
    now = datetime.now(timezone.utc).isoformat()
    company_id = f"cmp_{uuid.uuid4().hex}"
    doc = {
        "id": company_id,
        "workspace_id": workspace_id,
        "name": data.pop("name").strip(),
        "status": "active",
        "active": True,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
        **{k: v for k, v in data.items() if v is not None},
    }
    if doc.get("functional_currency"):
        doc["functional_currency"] = doc["functional_currency"].upper()
    if doc.get("jurisdiction"):
        doc["jurisdiction"] = doc["jurisdiction"].upper()
    await db.companies.insert_one(doc)
    return public_company(doc)


async def update_company_for_admin(db, company_id: str, user: dict, payload: CompanyUpdate) -> dict:
    current = await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_company(current)
    if "company_code" in changes:
        await _ensure_company_code_unique(db, workspace_id, changes.get("company_code"), exclude_id=company_id)
    if changes.get("name") is not None:
        changes["name"] = changes["name"].strip()
    if changes.get("functional_currency"):
        changes["functional_currency"] = changes["functional_currency"].upper()
    if changes.get("jurisdiction"):
        changes["jurisdiction"] = changes["jurisdiction"].upper()
    if "status" in changes:
        changes["active"] = changes["status"] == "active"
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.companies.update_one(
        {"workspace_id": workspace_id, "id": company_id},
        {"$set": changes},
    )
    updated = await db.companies.find_one({"workspace_id": workspace_id, "id": company_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Société introuvable")
    return public_company(updated)
