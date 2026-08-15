"""P3.3 — Account → Financial Concept mapping GOVERNANCE (client-scoped).

Maps normalized P2.3 accounts to canonical (P3.2 seeded, system-managed) concepts.

Effective windows are keyed by normalized financial periods (sequence), INCLUSIVE
on both ends (``effective_to_period_id`` = last covered period; open when null).
Cardinality: overlapping CONFIRMED windows for the same account are forbidden;
suggestions may overlap. ``unmapped`` is DERIVED (never stored). Confirmed
mappings are the only ones that will feed the Reporting Engine (P3.4).

Supersession is explicit and preserves history (no physical delete): confirming
a new OPEN mapping that starts after an existing OPEN one closes the prior at the
predecessor period. Any other overlap is a hard conflict (409) — never a silent
overwrite. Writes/confirm/reject/bulk/import require workspace admin; reads
require authorized company access. platform_role without membership has no
access; cross-workspace → 404. Never mutates Phase 2 / legacy collections.
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
INF = float("inf")

Source = Literal["manual", "excel", "api", "legacy", "rule", "suggested"]


class MappingCreate(BaseModel):
    account_id: str
    financial_concept_id: str
    effective_from_period_id: str
    effective_to_period_id: Optional[str] = None
    source: Source = "manual"
    status: Literal["suggested", "confirmed"] = "suggested"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None


class MappingUpdate(BaseModel):
    notes: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class BulkConfirmItem(BaseModel):
    mapping_id: Optional[str] = None
    account_id: Optional[str] = None
    financial_concept_id: Optional[str] = None
    effective_from_period_id: Optional[str] = None
    effective_to_period_id: Optional[str] = None


class BulkConfirm(BaseModel):
    items: list[BulkConfirmItem]
    dry_run: bool = False


def _public(doc):
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---- Reference lookups (read-only) ----------------------------------------
async def _period(db, ws, cid, pid, field="effective_from_period_id"):
    p = await db.financial_periods.find_one({"_id": pid, "workspace_id": ws, "company_id": cid})
    if not p:
        raise HTTPException(status_code=422, detail=f"{field} introuvable pour cette société")
    return p


async def _account(db, ws, cid, aid):
    a = await db.accounts.find_one({"_id": aid, "workspace_id": ws, "company_id": cid})
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


async def _predecessor(db, ws, cid, seq):
    docs = await db.financial_periods.find({"workspace_id": ws, "company_id": cid}).to_list(None)
    cand = [d for d in docs if (d.get("sequence") or 0) < seq]
    if not cand:
        return None
    return max(cand, key=lambda d: d.get("sequence") or 0)


def _overlap(f1, t1, f2, t2):
    hi1 = t1 if t1 is not None else INF
    hi2 = t2 if t2 is not None else INF
    return f1 <= hi2 and f2 <= hi1


def _effective_at(m, seq):
    fs = m.get("effective_from_sequence")
    ts = m.get("effective_to_sequence")
    if fs is None or seq < fs:
        return False
    return ts is None or seq <= ts


async def _resolve_window(db, ws, cid, from_pid, to_pid):
    fp = await _period(db, ws, cid, from_pid, "effective_from_period_id")
    fs = fp.get("sequence")
    ts, to_pid_val = None, None
    if to_pid:
        tp = await _period(db, ws, cid, to_pid, "effective_to_period_id")
        ts, to_pid_val = tp.get("sequence"), to_pid
        if fs is not None and ts is not None and fs > ts:
            raise HTTPException(status_code=422, detail="effective_from est postérieur à effective_to")
    return fs, ts, to_pid_val


async def _confirmed_for_account(db, ws, cid, account_id, exclude_id=None):
    docs = await db.account_mappings.find({
        "workspace_id": ws, "company_id": cid, "account_id": account_id,
        "status": CONFIRMED, "superseded": {"$ne": True}}).to_list(None)
    return [d for d in docs if d["_id"] != exclude_id]


async def _plan_confirm(db, ws, cid, account_id, F, T, exclude_id=None):
    """Returns list of mappings to supersede, or raises 409 on hard conflict."""
    to_supersede = []
    for m in await _confirmed_for_account(db, ws, cid, account_id, exclude_id):
        ef, et = m.get("effective_from_sequence"), m.get("effective_to_sequence")
        if not _overlap(F, T, ef, et):
            continue
        if T is None and et is None and ef is not None and ef < F:
            to_supersede.append(m)  # forward supersession (both open)
        else:
            raise HTTPException(status_code=409,
                                detail=f"Chevauchement avec un mapping confirmé existant ({m['_id']})")
    return to_supersede


async def _apply_supersession(db, to_supersede, new_id, F, ws, cid, now):
    superseded_ids = []
    for m in to_supersede:
        pred = await _predecessor(db, ws, cid, F)
        await db.account_mappings.update_one({"_id": m["_id"]}, {"$set": {
            "superseded": True, "superseded_by": new_id, "superseded_at": now,
            "effective_to_period_id": pred["_id"] if pred else None,
            "effective_to_sequence": (pred.get("sequence") if pred else F - 1)}})
        superseded_ids.append(m["_id"])
    return superseded_ids


# ---- Create / manual / confirm / reject -----------------------------------
async def create_mapping(db, company_id, user, payload: MappingCreate):
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    await _account(db, ws, company_id, payload.account_id)
    await _concept(db, payload.financial_concept_id)
    F, T, to_pid = await _resolve_window(db, ws, company_id, payload.effective_from_period_id,
                                         payload.effective_to_period_id)
    now = _now()
    mid = f"acm_{uuid.uuid4().hex}"
    to_supersede = []
    if payload.status == CONFIRMED:
        to_supersede = await _plan_confirm(db, ws, company_id, payload.account_id, F, T)
    doc = {
        "_id": mid, "workspace_id": ws, "company_id": company_id,
        "account_id": payload.account_id, "financial_concept_id": payload.financial_concept_id,
        "weight": 1.0,
        "effective_from_period_id": payload.effective_from_period_id, "effective_from_sequence": F,
        "effective_to_period_id": to_pid, "effective_to_sequence": T,
        "source": payload.source, "confidence": payload.confidence,
        "suggested_concept_id": payload.financial_concept_id if payload.status == SUGGESTED else None,
        "status": payload.status, "notes": payload.notes,
        "superseded": False, "superseded_by": None, "superseded_at": None, "supersedes_mapping_id": None,
        "created_by": user.get("id"), "created_at": now, "updated_at": now,
        "confirmed_by": None, "confirmed_at": None,
    }
    if payload.status == CONFIRMED:
        superseded = await _apply_supersession(db, to_supersede, mid, F, ws, company_id, now)
        doc["confirmed_by"], doc["confirmed_at"] = user.get("id"), now
        doc["supersedes_mapping_id"] = superseded[0] if superseded else None
        doc["_superseded_ids"] = superseded
    await db.account_mappings.insert_one({k: v for k, v in doc.items() if k != "_superseded_ids"})
    out = _public({k: v for k, v in doc.items() if k != "_superseded_ids"})
    out["superseded_ids"] = doc.get("_superseded_ids", [])
    return out


async def confirm_mapping(db, company_id, user, mapping_id: str):
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    if doc.get("superseded"):
        raise HTTPException(status_code=409, detail="Mapping remplacé — non modifiable")
    if doc.get("status") == REJECTED:
        raise HTTPException(status_code=409, detail="Mapping rejeté — non confirmable")
    if doc.get("status") == CONFIRMED:
        return {**_public(doc), "superseded_ids": []}
    await _concept(db, doc["financial_concept_id"])
    F, T = doc.get("effective_from_sequence"), doc.get("effective_to_sequence")
    to_supersede = await _plan_confirm(db, ws, company_id, doc["account_id"], F, T, exclude_id=mapping_id)
    now = _now()
    superseded = await _apply_supersession(db, to_supersede, mapping_id, F, ws, company_id, now)
    changes = {"status": CONFIRMED, "confirmed_by": user.get("id"), "confirmed_at": now, "updated_at": now,
               "supersedes_mapping_id": superseded[0] if superseded else None}
    await db.account_mappings.update_one({"_id": mapping_id}, {"$set": changes})
    doc.update(changes)
    return {**_public(doc), "superseded_ids": superseded}


async def reject_mapping(db, company_id, user, mapping_id: str, notes: Optional[str] = None):
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    if doc.get("superseded"):
        raise HTTPException(status_code=409, detail="Mapping remplacé — non modifiable")
    if doc.get("status") == CONFIRMED:
        raise HTTPException(status_code=409, detail="Impossible de rejeter un mapping confirmé (utilisez la supersession)")
    now = _now()
    changes = {"status": REJECTED, "rejected_by": user.get("id"), "rejected_at": now, "updated_at": now}
    if notes is not None:
        changes["notes"] = notes
    await db.account_mappings.update_one({"_id": mapping_id}, {"$set": changes})
    doc.update(changes)
    return _public(doc)


async def update_mapping(db, company_id, user, mapping_id: str, payload: MappingUpdate):
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    if doc.get("superseded"):
        raise HTTPException(status_code=409, detail="Mapping remplacé — non modifiable")
    changes = {}
    if payload.notes is not None:
        changes["notes"] = payload.notes
    if payload.confidence is not None:
        changes["confidence"] = payload.confidence
    if changes:
        changes["updated_at"] = _now()
        await db.account_mappings.update_one({"_id": mapping_id}, {"$set": changes})
        doc.update(changes)
    return _public(doc)


# ---- Bulk confirm ---------------------------------------------------------
async def bulk_confirm(db, company_id, user, payload: BulkConfirm):
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    results = []
    # Track windows confirmed within this batch to catch intra-batch conflicts.
    batch_confirmed = {}  # account_id -> list[(F,T)]

    for idx, item in enumerate(payload.items):
        ref = item.mapping_id or f"{item.account_id}->{item.financial_concept_id}"
        try:
            if item.mapping_id:
                doc = await db.account_mappings.find_one({
                    "_id": item.mapping_id, "workspace_id": ws, "company_id": company_id})
                if not doc:
                    raise HTTPException(status_code=404, detail="Mapping introuvable")
                if doc.get("superseded") or doc.get("status") == REJECTED:
                    raise HTTPException(status_code=409, detail="Mapping non confirmable")
                account_id = doc["account_id"]; concept_id = doc["financial_concept_id"]
                F, T = doc.get("effective_from_sequence"), doc.get("effective_to_sequence")
                already_confirmed = doc.get("status") == CONFIRMED
            else:
                if not (item.account_id and item.financial_concept_id and item.effective_from_period_id):
                    raise HTTPException(status_code=422, detail="account_id, financial_concept_id et effective_from_period_id requis")
                await _account(db, ws, company_id, item.account_id)
                await _concept(db, item.financial_concept_id)
                F, T, _to = await _resolve_window(db, ws, company_id, item.effective_from_period_id,
                                                  item.effective_to_period_id)
                account_id, concept_id = item.account_id, item.financial_concept_id
                already_confirmed = False
            # DB conflict check (excludes the mapping itself if id given)
            await _plan_confirm(db, ws, company_id, account_id, F, T, exclude_id=item.mapping_id)
            # Intra-batch conflict check
            for (bf, bt) in batch_confirmed.get(account_id, []):
                if _overlap(F, T, bf, bt):
                    raise HTTPException(status_code=409, detail="Conflit intra-lot pour ce compte")
            if not payload.dry_run:
                if item.mapping_id:
                    if not already_confirmed:
                        r = await confirm_mapping(db, company_id, user, item.mapping_id)
                    else:
                        r = {"id": item.mapping_id}
                else:
                    r = await create_mapping(db, company_id, user, MappingCreate(
                        account_id=account_id, financial_concept_id=concept_id,
                        effective_from_period_id=item.effective_from_period_id,
                        effective_to_period_id=item.effective_to_period_id,
                        source="manual", status=CONFIRMED))
                mid = r.get("id")
            else:
                mid = item.mapping_id
            batch_confirmed.setdefault(account_id, []).append((F, T))
            results.append({"ref": ref, "index": idx, "result": "confirmed", "mapping_id": mid})
        except HTTPException as e:
            results.append({"ref": ref, "index": idx, "result": "error",
                            "status_code": e.status_code, "reason": e.detail})

    summary = {"confirmed": sum(1 for r in results if r["result"] == "confirmed"),
               "errors": sum(1 for r in results if r["result"] == "error")}
    return {"company_id": company_id, "dry_run": payload.dry_run, "summary": summary, "results": results}


# ---- Reads / list / coverage / resolution ---------------------------------
async def _context_maps(db, ws, company_id):
    accounts = await db.accounts.find({"workspace_id": ws, "company_id": company_id}).to_list(None)
    concepts = await db.financial_concepts.find({}).to_list(None)
    amap = {a["_id"]: a for a in accounts}
    cmap = {c["_id"]: c for c in concepts}
    return amap, cmap


async def list_mappings(db, company_id, user, status=None, account_id=None, financial_concept_id=None,
                        source=None, effective_period_id=None, include_superseded=False):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    q = {"workspace_id": ws, "company_id": company_id}
    if status:
        q["status"] = status
    if account_id:
        q["account_id"] = account_id
    if financial_concept_id:
        q["financial_concept_id"] = financial_concept_id
    if source:
        q["source"] = source
    if not include_superseded:
        q["superseded"] = {"$ne": True}
    docs = await db.account_mappings.find(q).to_list(None)
    if effective_period_id:
        p = await _period(db, ws, company_id, effective_period_id, "effective_period_id")
        seq = p.get("sequence")
        docs = [d for d in docs if _effective_at(d, seq)]
    amap, cmap = await _context_maps(db, ws, company_id)
    out = []
    for d in sorted(docs, key=lambda d: (d.get("account_id") or "", d.get("created_at") or "")):
        pub = _public(d)
        a = amap.get(d.get("account_id")) or {}
        c = cmap.get(d.get("financial_concept_id")) or {}
        pub["account_code"] = a.get("account_code")
        pub["account_name"] = a.get("account_name")
        pub["concept_code"] = c.get("concept_code")
        out.append(pub)
    return {"company_id": company_id, "count": len(out), "mappings": out}


async def get_mapping(db, company_id, user, mapping_id: str):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.account_mappings.find_one({"_id": mapping_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Mapping introuvable")
    return _public(doc)


async def resolve_confirmed_mapping(db, ws, company_id, account_id, financial_period_id):
    """Deterministic: exactly one confirmed mapping effective at the period, or None.
    Multiple effective confirmed mappings = integrity error (500)."""
    p = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": company_id})
    if not p:
        raise HTTPException(status_code=422, detail="financial_period_id introuvable pour cette société")
    seq = p.get("sequence")
    docs = await db.account_mappings.find({
        "workspace_id": ws, "company_id": company_id, "account_id": account_id,
        "status": CONFIRMED}).to_list(None)
    effective = [d for d in docs if _effective_at(d, seq)]
    if len(effective) > 1:
        raise HTTPException(status_code=500,
                            detail=f"Intégrité: {len(effective)} mappings confirmés actifs pour {account_id}@{financial_period_id}")
    return _public(effective[0]) if effective else None


async def _tb_balances(db, ws, company_id, financial_period_id):
    """Latest completed TB import balances (abs ytd_net) per account_id. {} if none."""
    imports = await db.data_imports.find({
        "workspace_id": ws, "company_id": company_id, "data_type": "trial_balance",
        "financial_period_id": financial_period_id, "status": "completed"}).to_list(None)
    if not imports:
        return None
    latest = max(imports, key=lambda d: (d.get("completed_at") or "", d.get("_id") or ""))
    lines = await db.trial_balance_lines.find({
        "workspace_id": ws, "company_id": company_id, "import_id": latest["_id"]}).to_list(None)
    bal = {}
    for l in lines:
        aid = l.get("account_id")
        net = l.get("ytd_net")
        if net is None:
            net = (l.get("ytd_debit") or 0) - (l.get("ytd_credit") or 0)
        bal[aid] = bal.get(aid, 0.0) + abs(net or 0)
    return bal


async def mapping_coverage(db, company_id, user, financial_period_id=None):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    seq = None
    if financial_period_id:
        p = await _period(db, ws, company_id, financial_period_id, "financial_period_id")
        seq = p.get("sequence")
    accounts = await db.accounts.find({"workspace_id": ws, "company_id": company_id, "active": True}).to_list(None)
    maps = await db.account_mappings.find({"workspace_id": ws, "company_id": company_id}).to_list(None)
    confirmed, suggested, rejected = {}, {}, {}
    for m in maps:
        aid = m.get("account_id")
        st = m.get("status")
        if st == CONFIRMED:
            if seq is None:
                if not m.get("superseded"):
                    confirmed[aid] = m
            elif _effective_at(m, seq):
                confirmed[aid] = m
        elif st == SUGGESTED and not m.get("superseded"):
            suggested.setdefault(aid, m)
        elif st == REJECTED:
            rejected.setdefault(aid, m)
    mapped, suggested_only, rejected_only, unmapped = [], [], [], []
    for a in accounts:
        aid = a["_id"]
        entry = {"account_id": aid, "account_code": a.get("account_code"), "account_name": a.get("account_name")}
        if aid in confirmed:
            mapped.append({**entry, "financial_concept_id": confirmed[aid].get("financial_concept_id")})
        elif aid in suggested:
            suggested_only.append({**entry, "suggested_concept_id": suggested[aid].get("financial_concept_id")})
        elif aid in rejected:
            rejected_only.append(entry)
        else:
            unmapped.append(entry)
    total = len(accounts)
    result = {
        "company_id": company_id, "financial_period_id": financial_period_id,
        "denominator": "active normalized accounts",
        "total_active_accounts": total,
        "confirmed_accounts": len(mapped),
        "unmapped_accounts": len(unmapped) + len(suggested_only) + len(rejected_only),
        "suggested_only_accounts": len(suggested_only),
        "rejected_only_accounts": len(rejected_only),
        "coverage_percentage": round(100 * len(mapped) / total, 2) if total else 0.0,
        "fully_mapped": total > 0 and len(mapped) == total,
        "unmapped_details": unmapped + suggested_only + rejected_only,
        "mapped": mapped, "suggested_only": suggested_only,
        "rejected_only": rejected_only, "unmapped": unmapped,
    }
    # Optional materiality (does not gate basic coverage)
    if financial_period_id:
        bal = await _tb_balances(db, ws, company_id, financial_period_id)
        if bal is not None:
            mapped_ids = {m["account_id"] for m in mapped}
            mapped_bal = sum(v for aid, v in bal.items() if aid in mapped_ids)
            total_bal = sum(bal.values())
            unmapped_bal = total_bal - mapped_bal
            result["materiality"] = {
                "mapped_balance_abs": round(mapped_bal, 2),
                "unmapped_balance_abs": round(unmapped_bal, 2),
                "materiality_coverage_percentage": round(100 * mapped_bal / total_bal, 2) if total_bal else 0.0,
            }
            result["critical_unmapped_count"] = sum(
                1 for u in (unmapped + suggested_only + rejected_only)
                if (bal.get(u["account_id"], 0) or 0) > 0)
    return result


async def mapping_readiness(db, company_id, user, financial_period_id, template_code=None):
    """P3.4 readiness diagnostics — NO statement calculation, NO formula execution."""
    cov = await mapping_coverage(db, company_id, user, financial_period_id)
    ws = require_tenant_context(user)
    ready = cov["unmapped_accounts"] == 0 and cov["total_active_accounts"] > 0
    out = {"company_id": company_id, "financial_period_id": financial_period_id,
           "reporting_mapping_ready": ready, "coverage": cov}
    if template_code:
        tpl = await db.reporting_templates.find_one({"template_code": template_code, "scope": "system"})
        if tpl:
            lines = await db.reporting_template_lines.find({"template_id": tpl["_id"]}).to_list(None)
            needed = set()
            for l in lines:
                needed.update(l.get("concept_refs") or [])
            maps = await db.account_mappings.find({
                "workspace_id": ws, "company_id": company_id, "status": CONFIRMED,
                "superseded": {"$ne": True}}).to_list(None)
            p = await db.financial_periods.find_one({"_id": financial_period_id})
            seq = (p or {}).get("sequence")
            covered = {m["financial_concept_id"] for m in maps
                       if seq is None or _effective_at(m, seq)}
            missing = sorted(needed - covered)
            out["template_concept_coverage"] = {
                "template_code": template_code, "template_concepts": len(needed),
                "covered_concepts": len(needed & covered), "missing_concepts": missing}
    return out


async def ensure_indexes(db) -> None:
    await db.account_mappings.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_id", 1), ("status", 1)],
        name="idx_acm_account_status")
    # P3.3: multiple NON-OVERLAPPING confirmed windows per account are allowed,
    # so cardinality is enforced in application logic (_plan_confirm), NOT by a
    # unique index. Drop the P3.1 unique partial index if present.
    try:
        await db.account_mappings.drop_index("uniq_acm_confirmed_open")
    except Exception:
        pass
    await db.account_mappings.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_concept_id", 1)],
        name="idx_acm_concept")
