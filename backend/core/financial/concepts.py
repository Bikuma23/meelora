"""P3.1 — Financial Concepts (canonical, jurisdiction-neutral semantic layer).

SYSTEM-managed global referential: concepts carry FINANCIAL MEANING, never
presentation. concept_code is language-neutral and SEMANTICALLY IMMUTABLE once
created — the semantic meaning of a published concept is never mutated under a
new ``version``; evolution is done via deprecation + replacement. Only cosmetic
fields (sort_order, tags) may be updated. No physical delete (deprecate only).

Writes require a platform manager (platform_admin); reads require an
authenticated tenant user. platform_role NEVER grants access to client data.
This module NEVER touches Phase 2 collections or legacy acct_*/qc9434_*.
NO real seed here (that is P3.2).
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_platform_manager, require_tenant_context

ConceptType = Literal["asset", "liability", "equity", "income", "expense",
                       "contra_asset", "contra_liability"]
StatementType = Literal["balance_sheet", "income_statement"]
NormalBalance = Literal["debit", "credit"]
CashFlowCategory = Literal["operating", "investing", "financing", "none"]

ACTIVE = "active"
DEPRECATED = "deprecated"

# Semantic fields are immutable after creation (see module docstring).
_SEMANTIC_FIELDS = ("concept_code", "concept_type", "statement_type",
                    "natural_balance", "parent_concept_id", "is_aggregate",
                    "cash_flow_category")


class ConceptCreate(BaseModel):
    concept_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    concept_type: ConceptType
    statement_type: StatementType
    natural_balance: NormalBalance
    parent_concept_id: Optional[str] = None
    cash_flow_category: CashFlowCategory = "none"
    is_aggregate: bool = False
    sort_order: int = 0
    tags: list[str] = Field(default_factory=list)


class ConceptUpdate(BaseModel):
    sort_order: Optional[int] = None
    tags: Optional[list[str]] = None


def _public(doc: dict) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


async def create_concept(db, user, payload: ConceptCreate) -> dict:
    require_platform_manager(user)
    existing = await db.financial_concepts.find_one({"concept_code": payload.concept_code})
    if existing:
        raise HTTPException(status_code=409, detail=f"concept_code déjà utilisé: {payload.concept_code}")
    level = 0
    if payload.parent_concept_id:
        parent = await db.financial_concepts.find_one({"_id": payload.parent_concept_id})
        if not parent:
            raise HTTPException(status_code=422, detail="parent_concept_id introuvable")
        if parent.get("status") == DEPRECATED:
            raise HTTPException(status_code=422, detail="Le concept parent est déprécié")
        level = (parent.get("level") or 0) + 1
    now = _now()
    doc = {
        "_id": f"fc_{uuid.uuid4().hex}",
        "concept_code": payload.concept_code,
        "concept_type": payload.concept_type,
        "statement_type": payload.statement_type,
        "natural_balance": payload.natural_balance,
        "parent_concept_id": payload.parent_concept_id,
        "cash_flow_category": payload.cash_flow_category,
        "is_aggregate": payload.is_aggregate,
        "level": level,
        "sort_order": payload.sort_order,
        "tags": payload.tags,
        "scope": "system",
        "version": 1,
        "status": ACTIVE,
        "replaced_by_concept_id": None,
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.financial_concepts.insert_one(doc)
    return _public(doc)


async def update_concept(db, user, concept_id: str, payload: ConceptUpdate) -> dict:
    """Cosmetic-only update. Semantic mutation is forbidden (deprecate+replace)."""
    require_platform_manager(user)
    doc = await db.financial_concepts.find_one({"_id": concept_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Concept introuvable")
    if doc.get("status") == DEPRECATED:
        raise HTTPException(status_code=409, detail="Concept déprécié — non modifiable")
    changes = {}
    if payload.sort_order is not None:
        changes["sort_order"] = payload.sort_order
    if payload.tags is not None:
        changes["tags"] = payload.tags
    if not changes:
        return _public(doc)
    changes["updated_at"] = _now()
    changes["version"] = (doc.get("version") or 1) + 1
    await db.financial_concepts.update_one({"_id": concept_id}, {"$set": changes})
    doc.update(changes)
    return _public(doc)


async def deprecate_concept(db, user, concept_id: str, replaced_by_concept_id: Optional[str] = None) -> dict:
    """Semantic evolution path: deprecate a concept, optionally pointing to its
    replacement. Never physically deletes. concept_code stays reserved."""
    require_platform_manager(user)
    doc = await db.financial_concepts.find_one({"_id": concept_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Concept introuvable")
    if replaced_by_concept_id:
        rep = await db.financial_concepts.find_one({"_id": replaced_by_concept_id})
        if not rep:
            raise HTTPException(status_code=422, detail="replaced_by_concept_id introuvable")
        if rep.get("status") != ACTIVE:
            raise HTTPException(status_code=422, detail="Le concept de remplacement doit être actif")
    now = _now()
    changes = {"status": DEPRECATED, "replaced_by_concept_id": replaced_by_concept_id, "updated_at": now}
    await db.financial_concepts.update_one({"_id": concept_id}, {"$set": changes})
    doc.update(changes)
    return _public(doc)


async def list_concepts(db, user, statement_type: Optional[str] = None,
                        include_deprecated: bool = False) -> dict:
    require_tenant_context(user)  # authenticated tenant user; referential is global
    q = {}
    if statement_type:
        q["statement_type"] = statement_type
    if not include_deprecated:
        q["status"] = ACTIVE
    docs = await db.financial_concepts.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("statement_type") or "", d.get("level") or 0,
                             d.get("sort_order") or 0, d.get("concept_code") or ""))
    return {"count": len(docs), "concepts": [_public(d) for d in docs]}


async def get_concept(db, user, concept_id: str) -> dict:
    require_tenant_context(user)
    doc = await db.financial_concepts.find_one({"_id": concept_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Concept introuvable")
    return _public(doc)


async def ensure_indexes(db) -> None:
    await db.financial_concepts.create_index("concept_code", unique=True, name="uniq_concept_code")
    await db.financial_concepts.create_index(
        [("statement_type", 1), ("sort_order", 1)], name="idx_concept_statement_sort")
    await db.financial_concepts.create_index("parent_concept_id", name="idx_concept_parent")
