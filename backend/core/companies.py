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


# --- Extensible tax model (per jurisdiction). Backend stays permissive: it stores
# whatever tax_profile the caller sends, so new jurisdictions can be added without a
# schema change. Known Canadian keys are documented for the UI but never mandatory. ---
TAX_KEYS_BY_JURISDICTION = {
    "CA": ["bn", "gst", "qst", "pst"],   # BN, TPS/GST, TVQ/QST (QC), PST (BC/SK/MB)
    "CH": ["uid", "vat"],                # IDE/UID, TVA/MWST
}
CANONICAL_MODULES = {"REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)                       # nom d'affichage
    legal_name: Optional[str] = Field(default=None, max_length=250)       # nom légal
    trade_name: Optional[str] = Field(default=None, max_length=250)       # nom commercial
    company_code: Optional[str] = Field(default=None, max_length=80)
    entity_type: Optional[str] = Field(default=None, max_length=60)       # type d'entité (extensible)
    business_number: Optional[str] = Field(default=None, max_length=60)   # n° d'entreprise (BN/IDE...)
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    country: Optional[str] = Field(default=None, max_length=60)
    region: Optional[str] = Field(default=None, max_length=80)            # province / canton
    city: Optional[str] = Field(default=None, max_length=120)
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=200)
    functional_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    language: Optional[str] = Field(default=None, max_length=5)           # fr/en/de/it
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[Literal["operating", "holding", "real_estate", "nonprofit", "other"]] = None
    fiscal_year_start: Optional[str] = Field(default=None, max_length=5)
    subscribed_modules: Optional[list[str]] = None
    admin_email: Optional[str] = Field(default=None, max_length=200)      # administrateur à associer/inviter
    tax_profile: Optional[dict] = None                                   # extensible par juridiction


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=250)
    trade_name: Optional[str] = Field(default=None, max_length=250)
    company_code: Optional[str] = Field(default=None, max_length=80)
    entity_type: Optional[str] = Field(default=None, max_length=60)
    business_number: Optional[str] = Field(default=None, max_length=60)
    jurisdiction: Optional[str] = Field(default=None, max_length=10)
    country: Optional[str] = Field(default=None, max_length=60)
    region: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=120)
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=200)
    functional_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    language: Optional[str] = Field(default=None, max_length=5)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[Literal["operating", "holding", "real_estate", "nonprofit", "other"]] = None
    fiscal_year_start: Optional[str] = Field(default=None, max_length=5)
    subscribed_modules: Optional[list[str]] = None
    tax_profile: Optional[dict] = None
    status: Optional[Literal["active", "inactive"]] = None
    status_reason: Optional[str] = Field(default=None, max_length=500)


def public_company(doc: dict) -> dict:
    """Stable company API representation while preserving legacy compatibility."""
    return {
        "id": doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "name": doc.get("name") or doc.get("display_name") or doc.get("legal_name") or "",
        "legal_name": doc.get("legal_name"),
        "trade_name": doc.get("trade_name"),
        "display_name": doc.get("display_name") or doc.get("name"),
        "company_code": doc.get("company_code"),
        "entity_type": doc.get("entity_type"),
        "business_number": doc.get("business_number"),
        "jurisdiction": doc.get("jurisdiction"),
        "country": doc.get("country"),
        "region": doc.get("region"),
        "city": doc.get("city"),
        "address_line1": doc.get("address_line1"),
        "address_line2": doc.get("address_line2"),
        "postal_code": doc.get("postal_code"),
        "phone": doc.get("phone"),
        "email": doc.get("email"),
        "functional_currency": doc.get("functional_currency"),
        "language": doc.get("language"),
        "industry": doc.get("industry"),
        "company_type": doc.get("company_type"),
        "fiscal_year_start": doc.get("fiscal_year_start"),
        "subscribed_modules": doc.get("subscribed_modules") or [],
        "tax_profile": doc.get("tax_profile") or {},
        "branding": {
            "has_logo": bool((doc.get("branding") or {}).get("logo_document_id")),
            "logo_mime": (doc.get("branding") or {}).get("logo_mime"),
            "logo_updated_at": (doc.get("branding") or {}).get("logo_updated_at"),
        },
        "admin_email": doc.get("admin_email"),
        "status": doc.get("status", "active" if doc.get("active", True) else "inactive"),
        "active": doc.get("active", doc.get("status") != "inactive"),
        "status_reason": doc.get("status_reason"),
        "status_history": doc.get("status_history") or [],
        # Temporary compatibility bridge; removed with Financial Core migration.
        "legacy_prefix": doc.get("legacy_prefix"),
    }


def _clean_tax_profile(jurisdiction: Optional[str], tax_profile: Optional[dict]) -> dict:
    """Permissive, extensible-by-jurisdiction tax profile. Keeps only non-empty
    string values; never enforces a Canada-only shape."""
    if not isinstance(tax_profile, dict):
        return {}
    out = {}
    for k, v in tax_profile.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out


def _validate_modules(mods: Optional[list]) -> Optional[list]:
    if mods is None:
        return None
    invalid = [m for m in mods if m not in CANONICAL_MODULES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Modules inconnus: {', '.join(invalid)}")
    # de-dupe, keep canonical order
    order = ["REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"]
    return [m for m in order if m in set(mods)]


async def list_companies_for_user(db, user: dict, include_inactive: bool = False) -> list[dict]:
    workspace_id = require_tenant_context(user)
    # Admin registry with include_inactive: surface ALL workspace companies
    # (accessible-id resolution otherwise drops inactive ones).
    if include_inactive and user.get("role") == "admin":
        docs = await db.companies.find({"workspace_id": workspace_id}).to_list(None)
        docs.sort(key=lambda d: ((d.get("name") or d.get("display_name") or "").casefold(), d.get("id") or ""))
        return [public_company(d) for d in docs]
    accessible_ids = await list_accessible_company_ids(db, user)
    if not accessible_ids:
        return []
    query = {"workspace_id": workspace_id, "id": {"$in": accessible_ids}}
    if not include_inactive:
        query["active"] = {"$ne": False}
        query["status"] = {"$ne": "inactive"}
    docs = await db.companies.find(query).to_list(None)
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
    # Backend-gated: workspace admins OR platform administrators (platform authority).
    # `support` platform role and plain client users are refused here (fail-closed).
    if user.get("role") != "admin" and user.get("platform_role") != "platform_admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs (workspace ou plateforme)")
    workspace_id = require_tenant_context(user)
    data = payload.model_dump()
    await _ensure_company_code_unique(db, workspace_id, data.get("company_code"))
    data["subscribed_modules"] = _validate_modules(data.get("subscribed_modules"))
    data["tax_profile"] = _clean_tax_profile(data.get("jurisdiction"), data.get("tax_profile"))
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
    workspace_id = require_tenant_context(user)
    if user.get("platform_role") != "platform_admin" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    # Lifecycle management must reach INACTIVE companies too (reactivation),
    # so we look up by workspace scope without the active/status filter used by
    # operational access. Cross-workspace stays 404 (no tenant leak).
    current = await db.companies.find_one({"workspace_id": workspace_id, "id": company_id})
    if not current:
        raise HTTPException(status_code=404, detail="Société introuvable")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_company(current)
    # Status transition reason is metadata, not a plain settable field.
    reason = changes.pop("status_reason", None)
    if isinstance(reason, str):
        reason = reason.strip()
    if not changes and reason is None:
        return public_company(current)
    if "company_code" in changes:
        await _ensure_company_code_unique(db, workspace_id, changes.get("company_code"), exclude_id=company_id)
    if "subscribed_modules" in changes:
        changes["subscribed_modules"] = _validate_modules(changes.get("subscribed_modules"))
    if "tax_profile" in changes:
        changes["tax_profile"] = _clean_tax_profile(changes.get("jurisdiction") or current.get("jurisdiction"), changes.get("tax_profile"))
    if changes.get("name") is not None:
        changes["name"] = changes["name"].strip()
    if changes.get("functional_currency"):
        changes["functional_currency"] = changes["functional_currency"].upper()
    if changes.get("jurisdiction"):
        changes["jurisdiction"] = changes["jurisdiction"].upper()
    ops = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    if "status" in changes:
        changes["active"] = changes["status"] == "active"
        prev_status = current.get("status", "active" if current.get("active", True) else "inactive")
        if changes["status"] != prev_status:
            # Trace every status transition (deactivation AND reactivation).
            changes["status_reason"] = reason or ""
            ops["$push"] = {"status_history": {
                "at": now_iso,
                "from": prev_status,
                "to": changes["status"],
                "by_id": user.get("id"),
                "by": user.get("email") or user.get("name") or user.get("id"),
                "reason": reason or "",
            }}
    changes["updated_at"] = now_iso
    ops["$set"] = changes
    await db.companies.update_one(
        {"workspace_id": workspace_id, "id": company_id},
        ops,
    )
    updated = await db.companies.find_one({"workspace_id": workspace_id, "id": company_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Société introuvable")
    return public_company(updated)
