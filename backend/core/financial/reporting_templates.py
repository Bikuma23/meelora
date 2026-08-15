"""P3.1 — Reporting templates SKELETON + jurisdiction profiles.

Templates define PRESENTATION, never accounting storage. A template line
references canonical concepts (preferred) or, ONLY for custom (non-system)
templates, may reference accounts directly via ``semantic_bypass`` (flagged with
its limitations). System templates are platform-managed and global; custom
templates are workspace/company scoped, versioned, auditable and reversible.
Published versions are immutable (evolution = new version). NO calculation
engine here (that is P3.4) — only structure, validation, versioning, security.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import (require_company_access, require_company_admin,
                           require_platform_manager, require_tenant_context)
from .concepts import ACTIVE as CONCEPT_ACTIVE

DRAFT = "draft"
PUBLISHED = "published"
ARCHIVED = "archived"

StatementType = Literal["income_statement", "balance_sheet", "cash_flow"]
LineType = Literal["section", "concept", "subtotal", "formula", "spacer"]
DisplaySign = Literal["natural", "positive", "negative", "inverted"]
Measure = Literal["period", "ytd"]


class TemplateCreate(BaseModel):
    template_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    statement_type: StatementType
    scope: Literal["system", "workspace", "company"]
    jurisdiction: Optional[str] = Field(default=None, max_length=8)
    name: str = Field(min_length=1, max_length=160)
    based_on_template_id: Optional[str] = None


class TemplateLineCreate(BaseModel):
    line_code: str = Field(min_length=1, max_length=80)
    line_type: LineType
    parent_line_id: Optional[str] = None
    concept_refs: list[str] = Field(default_factory=list)
    account_refs: list[str] = Field(default_factory=list)
    semantic_bypass: bool = False
    formula: Optional[str] = None
    display_sign: DisplaySign = "natural"
    measure: Measure = "period"
    sort_order: int = 0


class JurisdictionProfileCreate(BaseModel):
    jurisdiction_code: str = Field(min_length=2, max_length=8)
    supported_frameworks: list[str] = Field(default_factory=list)
    default_locales: list[str] = Field(default_factory=list)
    default_template_codes: dict = Field(default_factory=dict)
    display_conventions: dict = Field(default_factory=dict)
    required_concepts: list[str] = Field(default_factory=list)
    optional_concepts: list[str] = Field(default_factory=list)


def _public(doc: dict) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---- Templates ------------------------------------------------------------
async def _authorize_template_write(db, user, scope, company_id):
    if scope == "system":
        require_platform_manager(user)
        return require_tenant_context(user) if user.get("workspace_id") else None
    if not company_id:
        raise HTTPException(status_code=422, detail="company_id requis pour un template custom")
    await require_company_admin(db, company_id, user)
    return require_tenant_context(user)


async def create_template(db, user, payload: TemplateCreate, company_id: Optional[str] = None) -> dict:
    ws = await _authorize_template_write(db, user, payload.scope, company_id)
    now = _now()
    doc = {
        "_id": f"rt_{uuid.uuid4().hex}",
        "template_code": payload.template_code,
        "statement_type": payload.statement_type,
        "scope": payload.scope,
        "jurisdiction": payload.jurisdiction,
        "workspace_id": None if payload.scope == "system" else ws,
        "company_id": None if payload.scope == "system" else company_id,
        "name": payload.name,
        "based_on_template_id": payload.based_on_template_id,
        "version": 1,
        "status": DRAFT,
        "created_by": user.get("id"), "created_at": now, "published_at": None,
    }
    await db.reporting_templates.insert_one(doc)
    return _public(doc)


async def _load_template_for_write(db, user, template_id):
    doc = await db.reporting_templates.find_one({"_id": template_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Template introuvable")
    await _authorize_template_write(db, user, doc.get("scope"), doc.get("company_id"))
    # For custom templates, enforce tenant isolation.
    if doc.get("scope") != "system":
        ws = require_tenant_context(user)
        if doc.get("workspace_id") != ws:
            raise HTTPException(status_code=404, detail="Template introuvable")
    return doc


async def add_template_line(db, user, template_id: str, payload: TemplateLineCreate) -> dict:
    tpl = await _load_template_for_write(db, user, template_id)
    if tpl.get("status") != DRAFT:
        raise HTTPException(status_code=409, detail="Seuls les templates en brouillon acceptent des lignes")

    if payload.line_type in ("subtotal", "formula") and not (payload.formula and payload.formula.strip()):
        raise HTTPException(status_code=422, detail="line_type=subtotal/formula exige une formule")

    uses_accounts = bool(payload.account_refs) or payload.semantic_bypass
    if uses_accounts and tpl.get("scope") == "system":
        raise HTTPException(status_code=422,
                            detail="semantic_bypass compte→ligne interdit pour les templates standards (système)")
    if payload.account_refs and not payload.semantic_bypass:
        raise HTTPException(status_code=422, detail="account_refs requiert semantic_bypass=true (custom uniquement)")

    if payload.line_type == "concept":
        if payload.semantic_bypass:
            if not payload.account_refs:
                raise HTTPException(status_code=422, detail="semantic_bypass exige account_refs")
        elif not payload.concept_refs:
            raise HTTPException(status_code=422, detail="line_type=concept exige concept_refs")

    for cid in payload.concept_refs:
        c = await db.financial_concepts.find_one({"_id": cid})
        if not c or c.get("status") != CONCEPT_ACTIVE:
            raise HTTPException(status_code=422, detail=f"concept_ref invalide/inactif: {cid}")
    if payload.semantic_bypass and tpl.get("company_id"):
        for aid in payload.account_refs:
            a = await db.accounts.find_one({"_id": aid, "company_id": tpl.get("company_id")})
            if not a:
                raise HTTPException(status_code=422, detail=f"account_ref introuvable: {aid}")

    now = _now()
    doc = {
        "_id": f"rtl_{uuid.uuid4().hex}",
        "template_id": template_id,
        "line_code": payload.line_code,
        "line_type": payload.line_type,
        "parent_line_id": payload.parent_line_id,
        "concept_refs": payload.concept_refs,
        "account_refs": payload.account_refs,
        "semantic_bypass": payload.semantic_bypass,
        "semantic_bypass_warning": ("Contournement sémantique : cette ligne référence des comptes "
                                    "directement et n'alimentera pas les concepts (KPI/Cash Flow)."
                                    ) if payload.semantic_bypass else None,
        "formula": payload.formula,
        "display_sign": payload.display_sign,
        "measure": payload.measure,
        "sort_order": payload.sort_order,
        "created_at": now,
    }
    await db.reporting_template_lines.insert_one(doc)
    return _public(doc)


async def publish_template(db, user, template_id: str) -> dict:
    tpl = await _load_template_for_write(db, user, template_id)
    if tpl.get("status") != DRAFT:
        raise HTTPException(status_code=409, detail="Seul un brouillon peut être publié")
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    if not lines:
        raise HTTPException(status_code=422, detail="Un template publié doit contenir au moins une ligne")
    now = _now()
    await db.reporting_templates.update_one({"_id": template_id},
                                            {"$set": {"status": PUBLISHED, "published_at": now}})
    tpl.update({"status": PUBLISHED, "published_at": now})
    return _public(tpl)


async def archive_template(db, user, template_id: str) -> dict:
    tpl = await _load_template_for_write(db, user, template_id)
    await db.reporting_templates.update_one({"_id": template_id}, {"$set": {"status": ARCHIVED}})
    tpl["status"] = ARCHIVED
    return _public(tpl)


async def new_template_version(db, user, template_id: str) -> dict:
    """Immutable evolution: clone a published template into a new draft version."""
    tpl = await _load_template_for_write(db, user, template_id)
    if tpl.get("status") != PUBLISHED:
        raise HTTPException(status_code=409, detail="Seul un template publié peut être versionné")
    now = _now()
    new_id = f"rt_{uuid.uuid4().hex}"
    clone = {**{k: v for k, v in tpl.items() if k != "_id"},
             "_id": new_id, "version": (tpl.get("version") or 1) + 1, "status": DRAFT,
             "based_on_template_id": template_id, "created_at": now, "published_at": None,
             "created_by": user.get("id")}
    await db.reporting_templates.insert_one(clone)
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    for l in lines:
        nl = {**{k: v for k, v in l.items() if k != "_id"}, "_id": f"rtl_{uuid.uuid4().hex}",
              "template_id": new_id, "created_at": now}
        await db.reporting_template_lines.insert_one(nl)
    return _public(clone)


async def list_system_templates(db, user, jurisdiction: Optional[str] = None,
                                 statement_type: Optional[str] = None) -> dict:
    require_tenant_context(user)
    q = {"scope": "system"}
    if jurisdiction:
        q["jurisdiction"] = jurisdiction
    if statement_type:
        q["statement_type"] = statement_type
    docs = await db.reporting_templates.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("template_code") or "", d.get("version") or 0))
    return {"count": len(docs), "templates": [_public(d) for d in docs]}


async def list_company_templates(db, company_id, user, statement_type: Optional[str] = None) -> dict:
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    q = {"workspace_id": ws, "company_id": company_id, "scope": {"$in": ["workspace", "company"]}}
    if statement_type:
        q["statement_type"] = statement_type
    docs = await db.reporting_templates.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("template_code") or "", d.get("version") or 0))
    return {"company_id": company_id, "count": len(docs), "templates": [_public(d) for d in docs]}


async def get_template(db, user, template_id: str) -> dict:
    doc = await db.reporting_templates.find_one({"_id": template_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Template introuvable")
    if doc.get("scope") == "system":
        require_tenant_context(user)
    else:
        await require_company_access(db, doc.get("company_id"), user)
        ws = require_tenant_context(user)
        if doc.get("workspace_id") != ws:
            raise HTTPException(status_code=404, detail="Template introuvable")
    lines = await db.reporting_template_lines.find({"template_id": template_id}).to_list(None)
    lines.sort(key=lambda d: (d.get("sort_order") or 0, d.get("line_code") or ""))
    out = _public(doc)
    out["lines"] = [_public(l) for l in lines]
    return out


# ---- Jurisdiction profiles (system-managed) -------------------------------
async def create_jurisdiction_profile(db, user, payload: JurisdictionProfileCreate) -> dict:
    require_platform_manager(user)
    existing = await db.jurisdiction_profiles.find_one({"jurisdiction_code": payload.jurisdiction_code})
    if existing:
        raise HTTPException(status_code=409, detail="Profil de juridiction déjà existant")
    now = _now()
    doc = {"_id": f"jp_{payload.jurisdiction_code}", "jurisdiction_code": payload.jurisdiction_code,
           "scope": "system", "supported_frameworks": payload.supported_frameworks,
           "default_locales": payload.default_locales, "default_template_codes": payload.default_template_codes,
           "display_conventions": payload.display_conventions, "required_concepts": payload.required_concepts,
           "optional_concepts": payload.optional_concepts, "version": 1, "status": "active",
           "created_by": user.get("id"), "created_at": now, "updated_at": now}
    await db.jurisdiction_profiles.insert_one(doc)
    return _public(doc)


async def list_jurisdiction_profiles(db, user) -> dict:
    require_tenant_context(user)
    docs = await db.jurisdiction_profiles.find({"scope": "system"}).to_list(None)
    docs.sort(key=lambda d: d.get("jurisdiction_code") or "")
    return {"count": len(docs), "profiles": [_public(d) for d in docs]}


async def get_jurisdiction_profile(db, user, jurisdiction_code: str) -> dict:
    require_tenant_context(user)
    doc = await db.jurisdiction_profiles.find_one({"jurisdiction_code": jurisdiction_code, "scope": "system"})
    if not doc:
        raise HTTPException(status_code=404, detail="Profil de juridiction introuvable")
    return _public(doc)


async def ensure_indexes(db) -> None:
    await db.reporting_templates.create_index(
        [("template_code", 1), ("version", 1)], unique=True, name="uniq_template_code_version")
    await db.reporting_templates.create_index(
        [("scope", 1), ("workspace_id", 1), ("company_id", 1), ("statement_type", 1)],
        name="idx_template_scope")
    await db.reporting_template_lines.create_index(
        [("template_id", 1), ("sort_order", 1)], name="idx_template_line_order")
    await db.jurisdiction_profiles.create_index(
        "jurisdiction_code", unique=True, name="uniq_jurisdiction_code")
