"""P3.1 — Account → Financial Concept mappings (client-scoped governance).

Maps normalized P2.3 accounts to canonical concepts. Cardinality: at most ONE
``confirmed`` (non-superseded) mapping per account for a given effective window
(splits prepared via ``weight`` but NOT activated). Effective windows are keyed
by ``financial_period_id`` (denormalized sequence) to stay consistent with the
Financial Core. ``unmapped`` is DERIVED, never stored: stored statuses are
suggested / confirmed / rejected. No physical delete (supersession only).

Writes/confirm/reject require workspace admin; reads require authorized company
access. platform_role without membership has no access. This module never
mutates Phase 2 collections; it only reads accounts / financial_periods /
financial_concepts and writes ``account_mappings``.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .concepts import ACTIVE as CONCEPT_ACTIVE

SUGGESTED = "suggested"
CONFIRMED = "confirmed"
REJECTED = "rejected"
UNMAPPED = "unmapped"  # DERIVED only, never stored

Source = Literal["manual", "excel", "api", "legacy", "rule", "suggested"]


class MappingCreate(BaseModel):
    account_id: str
    financial_concept_id: str
    effective_from_period_id: str
    source: Source = "manual"
    status: Literal["suggested", "confirmed"] = "suggested"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None


def _public(doc: dict) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _period(db, ws, company_id, period_id):
    p = await db.financial_periods.find_one({
        "_id": period_id, "workspace_id": ws, "company_id": company_id})
    if not p:
        raise HTTPException(status_code=422, detail="effective_from_period_id introuvable pour cette société")
    return p


async def _account(db, ws, company_id, account_id):
    a = await db.accounts.find_one({"_id": account_id, "workspace_id": ws, "company_id": company_id})
    if not a:
        raise HTTPException(status_code=422, detail="account_id introuvable pour cette société")
    return a


async def _concept(db, concept_id):
    c = await db.financial_concepts.find_one({"_id": concept_id})
    if not c:
        raise HTTPException(status_code=422, detail="financial_concept_id introuvable")
    if c.get("status") != CONCEPT_ACTIVE:
        raise HTTPException(status_code=422, detail="Le concept n'est pas actif")
    if c.get("is_aggregate"):
        raise HTTPException(status_code=422, detail="Un concept agrégat n'est pas mappable directement")
    return c


async def _open_confirmed(db, ws, company_id, account_id):
    docs = await db.account_mappings.find({
        "workspace_id": ws, "company_id": company_id, "account_id": account_id,
        "status": CONFIRMED, "superseded": {"$ne": True}}).to_list(None)
    return docs[0] if docs else None


async def _supersede_open_confirmed(db, ws, company_id, account_id, new_id, new_from_period_id, new_from_seq):
    prior = await _open_confirmed(db, ws, company_id, account_id)
    if not prior:
        return None
    if (new_from_seq or 0) < (prior.get("effective_from_sequence") or 0):
        raise HTTPException(status_code=409,
                            detail="Antidatage interdit : la nouvelle fenêtre précède le mapping confirmé actif")
    now = _now()
    await db.account_mappings.update_one({"_id": prior["_id"]}, {"$set": {
        "superseded": True, "superseded_by": new_id, "superseded_at": now,
        "effective_to_period_id": new_from_period_id, "effective_to_sequence": new_from_seq}})
    return prior["_id"]


async def create_mapping(db, company_id, user, payload: MappingCreate) -> dict:
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    await _account(db, ws, company_id, payload.account_id)
    await _concept(db, payload.financial_concept_id)
    period = await _period(db, ws, company_id, payload.effective_from_period_id)
    from_seq = period.get("sequence")
    now = _now()
    doc = {
        "_id": f"acm_{uuid.uuid4().hex}",
        "workspace_id": ws, "company_id": company_id,
        "account_id": payload.account_id,
        "financial_concept_id": payload.financial_concept_id,
        "weight": 1.0,  # splits prepared, not activated
        "effective_from_period_id": payload.effective_from_period_id,
        "effective_from_sequence": from_seq,
        "effective_to_period_id": None, "effective_to_sequence": None,
        "source": payload.source,
        "confidence": payload.confidence,
        "suggested_concept_id": payload.financial_concept_id if payload.status == SUGGESTED else None,
        "status": payload.status,
        "notes": payload.notes,
        "superseded": False, "superseded_by": None, "superseded_at": None,
        "created_by": user.get("id"), "created_at": now,
        "confirmed_by": None, "confirmed_at": None,
    }
    if payload.status == CONFIRMED:
        supersedes = await _supersede_open_confirmed(db, ws, company_id, payload.account_id,
                                                     doc["_id"], payload.effective_from_period_id, from_seq)
        doc["supersedes_mapping_id"] = supersedes
        doc["confirmed_by"] = user.get("id")
        doc["confirmed_at"] = now
    await db.account_mappings.insert_one(doc)
    return _public(doc)


async def confirm_mapping(db, company_id, user, mapping_id: str) -> dict:
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    if doc.get("superseded"):
        raise HTTPException(status_code=409, detail="Mapping remplacé — non modifiable")
    if doc.get("status") == CONFIRMED:
        return _public(doc)
    # Re-validate concept still mappable at confirmation time.
    await _concept(db, doc["financial_concept_id"])
    supersedes = await _supersede_open_confirmed(db, ws, company_id, doc["account_id"], mapping_id,
                                                 doc["effective_from_period_id"], doc.get("effective_from_sequence"))
    now = _now()
    changes = {"status": CONFIRMED, "confirmed_by": user.get("id"), "confirmed_at": now,
               "supersedes_mapping_id": supersedes}
    await db.account_mappings.update_one({"_id": mapping_id}, {"$set": changes})
    doc.update(changes)
    return _public(doc)


async def reject_mapping(db, company_id, user, mapping_id: str, notes: Optional[str] = None) -> dict:
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    if doc.get("superseded"):
        raise HTTPException(status_code=409, detail="Mapping remplacé — non modifiable")
    now = _now()
    changes = {"status": REJECTED, "rejected_by": user.get("id"), "rejected_at": now}
    if notes is not None:
        changes["notes"] = notes
    await db.account_mappings.update_one({"_id": mapping_id}, {"$set": changes})
    doc.update(changes)
    return _public(doc)


async def list_mappings(db, company_id, user, status: Optional[str] = None,
                        account_id: Optional[str] = None, include_superseded: bool = False) -> dict:
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    q = {"workspace_id": ws, "company_id": company_id}
    if status:
        q["status"] = status
    if account_id:
        q["account_id"] = account_id
    if not include_superseded:
        q["superseded"] = {"$ne": True}
    docs = await db.account_mappings.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("account_id") or "", d.get("created_at") or ""))
    return {"company_id": company_id, "count": len(docs), "mappings": [_public(d) for d in docs]}


async def get_mapping(db, company_id, user, mapping_id: str) -> dict:
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    return _public(doc)


def _effective_at(doc, seq):
    f = doc.get("effective_from_sequence")
    t = doc.get("effective_to_sequence")
    if f is None:
        return False
    if seq < f:
        return False
    if t is not None and seq >= t:
        return False
    return True


async def mapping_coverage(db, company_id, user, financial_period_id: Optional[str] = None) -> dict:
    """DERIVES unmapped/suggested_only/mapped from accounts vs confirmed mappings.

    If a period is supplied, effectiveness is evaluated at that period's sequence
    (historical windows honored). Otherwise open confirmed mappings are used."""
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    seq = None
    if financial_period_id:
        p = await _period(db, ws, company_id, financial_period_id)
        seq = p.get("sequence")
    accounts = await db.accounts.find({"workspace_id": ws, "company_id": company_id, "active": True}).to_list(None)
    all_maps = await db.account_mappings.find({"workspace_id": ws, "company_id": company_id}).to_list(None)
    confirmed_by_acct, suggested_by_acct = {}, {}
    for m in all_maps:
        aid = m.get("account_id")
        if m.get("status") == CONFIRMED:
            if seq is None:
                if not m.get("superseded"):
                    confirmed_by_acct[aid] = m
            elif _effective_at(m, seq):
                confirmed_by_acct[aid] = m
        elif m.get("status") == SUGGESTED and not m.get("superseded"):
            suggested_by_acct.setdefault(aid, m)
    mapped, suggested_only, unmapped = [], [], []
    for a in accounts:
        aid = a["_id"]
        code = a.get("account_code")
        if aid in confirmed_by_acct:
            mapped.append({"account_id": aid, "account_code": code,
                           "financial_concept_id": confirmed_by_acct[aid].get("financial_concept_id")})
        elif aid in suggested_by_acct:
            suggested_only.append({"account_id": aid, "account_code": code,
                                   "suggested_concept_id": suggested_by_acct[aid].get("financial_concept_id")})
        else:
            unmapped.append({"account_id": aid, "account_code": code})
    total = len(accounts)
    return {
        "company_id": company_id, "financial_period_id": financial_period_id,
        "total_active_accounts": total,
        "counts": {"mapped": len(mapped), "suggested_only": len(suggested_only), "unmapped": len(unmapped)},
        "coverage_ratio": round(len(mapped) / total, 4) if total else 0.0,
        "fully_mapped": len(unmapped) == 0 and len(suggested_only) == 0,
        "mapped": mapped, "suggested_only": suggested_only, "unmapped": unmapped,
    }


async def ensure_indexes(db) -> None:
    await db.account_mappings.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_id", 1), ("status", 1)],
        name="idx_acm_account_status")
    # At most one confirmed, non-superseded mapping per account (cardinality).
    await db.account_mappings.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_id", 1)],
        unique=True, name="uniq_acm_confirmed_open",
        partialFilterExpression={"status": CONFIRMED, "superseded": False})
    await db.account_mappings.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_concept_id", 1)],
        name="idx_acm_concept")
