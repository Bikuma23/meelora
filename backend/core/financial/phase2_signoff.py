"""P2.10 — Phase 2 sign-off / validation-evidence layer.

Freezes the diagnostic evidence produced by P2.9 reconciliation into an
auditable, immutable Phase 2 completion record. Introduces NO new financial
calculation: readiness is derived exclusively from the real output of
``reconciliation_status`` (P2.9). NEVER changes ``financial_data_source`` (no
cutover here — readiness only) and NEVER writes to legacy financial collections
(acct_* / qc9434_*). The only collection written is ``phase2_signoffs``.

Finalized sign-offs are audit evidence: they are never physically deleted. A
later sign-off for the same company/period supersedes (never overwrites) the
previous one, so the latest finalized record is deterministic.
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .reconciliation import (
    reconciliation_status, reconcile_journal_vs_tb,
    RECONCILED, DIFFERENCE, INCOMPLETE, NOT_AVAILABLE,
)

APPROVED = "approved"
APPROVED_WITH_CONDITIONS = "approved_with_conditions"
BLOCKED = "blocked"
VALID_DECISIONS = {APPROVED, APPROVED_WITH_CONDITIONS, BLOCKED}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hard_gate(recon: dict):
    """Trial-Balance / cutover gates that must hold for any approval.

    Returns (ok: bool, reasons: list[str]). These are the non-negotiable gates:
    a broken Trial Balance can NEVER be approved (even with conditions)."""
    tb = recon.get("trial_balance_status")
    critical = recon.get("critical_difference_count", 0)
    reasons = []
    if tb != RECONCILED:
        reasons.append(f"balance non réconciliée (statut={tb})")
    if not recon.get("cutover_ready"):
        reasons.append("cutover_ready=false")
    if critical > 0:
        reasons.append(f"{critical} écart(s) critique(s) de mapping de comptes")
    return (len(reasons) == 0), reasons


def _build_snapshot(recon: dict, journal: dict, tolerance: float) -> dict:
    """Immutable evidence/metadata — NOT a duplication of financial datasets."""
    coverage = journal.get("coverage", {}) if isinstance(journal, dict) else {}
    return {
        "reconciliation_generated_at": recon.get("generated_at"),
        "normalized_import_id": recon.get("normalized_import_id"),
        "legacy_period_key": recon.get("legacy_source_metadata", {}).get("legacy_period_key"),
        "legacy_columns_mapped": recon.get("legacy_source_metadata", {}).get("legacy_columns_mapped"),
        "tolerance": tolerance,
        "accounts_status": recon.get("accounts_status"),
        "accounts_summary": recon.get("difference_counts", {}).get("accounts", {}),
        "trial_balance_status": recon.get("trial_balance_status"),
        "trial_balance_control_totals": recon.get("control_totals", {}),
        "difference_counts": recon.get("difference_counts", {}),
        "critical_difference_count": recon.get("critical_difference_count", 0),
        "journal_status": recon.get("journal_status"),
        "journal_coverage": coverage,
        "overall_status": recon.get("overall_status"),
        "cutover_ready": recon.get("cutover_ready"),
    }


async def _latest_signoff(db, ws, company_id, financial_period_id):
    docs = await db.phase2_signoffs.find({
        "workspace_id": ws, "company_id": company_id,
        "financial_period_id": financial_period_id, "superseded": {"$ne": True}}).to_list(None)
    if not docs:
        return None
    docs.sort(key=lambda d: (d.get("created_at") or "", d.get("_id") or ""))
    return docs[-1]


def _public(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items()}
    out["id"] = out.pop("_id", None)
    return out


# ---- Create / finalize (workspace admin only) -----------------------------
async def create_signoff(db, company_id, user, *, financial_period_id, decision,
                         conditions=None, notes=None, normalized_import_id=None,
                         tolerance=0.01, legacy_period_key=None, legacy_cols=None):
    """Create a finalized Phase 2 sign-off backed by real P2.9 output.

    Returns the created record (public shape). Raises 422 when the requested
    decision is not permitted by the reconciliation evidence."""
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")
    if decision not in VALID_DECISIONS:
        raise HTTPException(status_code=422,
                            detail=f"Décision invalide: {decision} (attendu {'|'.join(sorted(VALID_DECISIONS))})")
    period = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": ws, "company_id": company_id})
    if not period:
        raise HTTPException(status_code=404, detail="Période introuvable")

    conditions = [c for c in (conditions or []) if str(c).strip()]

    # Consume REAL P2.9 output (never recomputed by hand).
    recon = await reconciliation_status(
        db, company_id, user, financial_period_id, normalized_import_id=normalized_import_id,
        tolerance=tolerance, legacy_period_key=legacy_period_key, legacy_cols=legacy_cols)
    journal = await reconcile_journal_vs_tb(
        db, company_id, user, financial_period_id,
        normalized_import_id=normalized_import_id, tolerance=tolerance)

    hard_ok, hard_reasons = _hard_gate(recon)
    journal_status = recon.get("journal_status")

    # ---- Decision validation --------------------------------------------
    if decision == APPROVED:
        if not hard_ok:
            raise HTTPException(status_code=422, detail={
                "message": "Approbation refusée : préconditions de réconciliation non satisfaites",
                "reasons": hard_reasons})
        if journal_status != RECONCILED:
            raise HTTPException(status_code=422, detail={
                "message": ("Journal non réconcilié — une approbation simple n'est pas autorisée. "
                            "Utilisez approved_with_conditions avec une condition documentée."),
                "reasons": [f"journal statut={journal_status}"]})
    elif decision == APPROVED_WITH_CONDITIONS:
        if not conditions:
            raise HTTPException(status_code=422,
                                detail="approved_with_conditions exige au moins une condition explicite")
        if not hard_ok:
            raise HTTPException(status_code=422, detail={
                "message": "Approbation sous conditions refusée : la balance doit être réconciliée (cutover_ready) au préalable",
                "reasons": hard_reasons})
    # BLOCKED is always permitted; it preserves reconciliation reasons.

    reasons = hard_reasons[:]
    if journal_status != RECONCILED:
        reasons.append(f"journal statut={journal_status}")

    now = _now()
    doc = {
        "_id": f"p2so_{uuid.uuid4().hex}",
        "workspace_id": ws,
        "company_id": company_id,
        "financial_period_id": financial_period_id,
        "normalized_import_id": recon.get("normalized_import_id"),
        "legacy_period_key": legacy_period_key,
        "accounts_status": recon.get("accounts_status"),
        "trial_balance_status": recon.get("trial_balance_status"),
        "journal_status": journal_status,
        "cutover_ready": recon.get("cutover_ready"),
        "decision": decision,
        "conditions": conditions,
        "notes": notes,
        "reconciliation_reasons": reasons if decision == BLOCKED else [],
        "validation_snapshot": _build_snapshot(recon, journal, tolerance),
        "supersedes_signoff_id": None,
        "superseded": False,
        "superseded_at": None,
        "validated_by": user.get("id"),
        "validated_at": now,
        "created_at": now,
    }

    # Supersession: mark the prior latest finalized record (any decision).
    prior = await _latest_signoff(db, ws, company_id, financial_period_id)
    if prior:
        doc["supersedes_signoff_id"] = prior["_id"]
        await db.phase2_signoffs.update_one(
            {"_id": prior["_id"]},
            {"$set": {"superseded": True, "superseded_at": now, "superseded_by": doc["_id"]}})

    await db.phase2_signoffs.insert_one(doc)
    return _public(doc)


# ---- Reads (authorized company members) -----------------------------------
async def list_signoffs(db, company_id, user, financial_period_id=None):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    q = {"workspace_id": ws, "company_id": company_id}
    if financial_period_id:
        q["financial_period_id"] = financial_period_id
    docs = await db.phase2_signoffs.find(q).to_list(None)
    docs.sort(key=lambda d: (d.get("created_at") or "", d.get("_id") or ""), reverse=True)
    return {"company_id": company_id, "count": len(docs), "signoffs": [_public(d) for d in docs]}


async def get_signoff(db, company_id, user, signoff_id):
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    doc = await db.phase2_signoffs.find_one({
        "_id": signoff_id, "workspace_id": ws, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Sign-off introuvable")
    return _public(doc)


async def signoff_status(db, company_id, user, financial_period_id):
    """Latest finalized (non-superseded) sign-off + count for a period."""
    await require_company_access(db, company_id, user)
    ws = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")
    latest = await _latest_signoff(db, ws, company_id, financial_period_id)
    total = await db.phase2_signoffs.count_documents({
        "workspace_id": ws, "company_id": company_id, "financial_period_id": financial_period_id})
    return {
        "company_id": company_id,
        "financial_period_id": financial_period_id,
        "has_signoff": latest is not None,
        "latest_signoff": _public(latest) if latest else None,
        "signoff_count": total,
    }


async def ensure_indexes(db) -> None:
    await db.phase2_signoffs.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_period_id", 1)],
        name="idx_phase2_signoffs_period")
    await db.phase2_signoffs.create_index(
        [("workspace_id", 1), ("company_id", 1), ("superseded", 1)],
        name="idx_phase2_signoffs_latest")
