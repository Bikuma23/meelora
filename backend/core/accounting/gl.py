"""ACCOUNTING A2 — operational GL workflow, ALIGNED on the Financial Core P2.

This layer owns the *pre-posting workflow only* (document, approvals, provenance,
maker-checker). It is NOT a second general ledger.

Periods  → canonical ``financial_periods`` (P2.2). This module NEVER maintains a
           second accounting calendar; there is no ``gl_periods`` collection.
Entries  → ``accounting_entries`` (workflow document). Lifecycle:
           draft → submitted → approved → posted → reversed.
Ledger   → at POST, exactly ONE canonical journal entry is created in the
           normalized journal ``journal_entries`` / ``journal_entry_lines`` (P2.6)
           and linked immutably via ``journal_entry_id``. POST is idempotent.
Reversal → creates a NEW accounting_entry AND a NEW canonical journal entry,
           linked to the originals; a posted journal entry is never mutated
           (only a non-financial back-reference link is added).

Period rules (ported onto the canonical source): open → locked, locked → open,
open → closed, locked → closed. ``closed`` is TERMINAL (reopening forbidden for
everyone). Posting requires an OPEN period and every EARLIER period closed.

Authorization is enforced at the routes (module access + sensitive permissions +
maker-checker below). Legacy financial data (acct_*, qc9434_*) is never touched.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from ..financial import journal as journal_service
from ..financial.periods import _ALLOWED_TRANSITIONS

ENTRY_STATUSES = ("draft", "submitted", "approved", "posted", "reversed")
PERIOD_STATUSES = ("open", "locked", "closed")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Montant invalide")


def _period_public(d: dict) -> dict:
    """Canonical financial_period rendered for the Accounting workflow UI.
    ``code`` is aliased from the canonical ``period_code`` (no duplicate field)."""
    return {
        "id": d.get("_id") or d.get("id"),
        "workspace_id": d.get("workspace_id"),
        "company_id": d.get("company_id"),
        "financial_year_id": d.get("financial_year_id"),
        "financial_period_id": d.get("_id") or d.get("id"),
        "code": d.get("period_code"),
        "label": d.get("label"),
        "start_date": d.get("start_date"),
        "end_date": d.get("end_date"),
        "sequence": d.get("sequence"),
        "status": d.get("status", "open"),
    }


def public_entry(d: dict) -> dict:
    return {
        "id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
        "period_id": d.get("period_id"), "financial_period_id": d.get("financial_period_id"),
        "financial_year_id": d.get("financial_year_id"),
        "date": d.get("date"), "memo": d.get("memo"),
        "reference": d.get("reference"), "source": d.get("source", "manual"),
        "status": d.get("status", "draft"), "lines": d.get("lines", []),
        "total_debit": d.get("total_debit"), "total_credit": d.get("total_credit"),
        "created_by": d.get("created_by"), "created_at": d.get("created_at"),
        "submitted_by": d.get("submitted_by"), "approved_by": d.get("approved_by"),
        "posted_by": d.get("posted_by"), "reversed_by": d.get("reversed_by"),
        "reversal_of": d.get("reversal_of"), "reversed_by_entry": d.get("reversed_by_entry"),
        # Immutable link to the canonical journal (P2.6) — bidirectional traceability.
        "journal_entry_id": d.get("journal_entry_id"),
        "reversal_journal_entry_id": d.get("reversal_journal_entry_id"),
        "attachments": d.get("attachments", []), "audit": d.get("audit", []),
    }


# --------------------------------------------------------------------------- #
# Periods — canonical financial_periods only (NO gl_periods)
# --------------------------------------------------------------------------- #
async def list_periods(db, workspace_id, company_id):
    docs = await db.financial_periods.find(
        {"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    docs.sort(key=lambda d: (d.get("start_date") or "", d.get("sequence") or 0))
    return [_period_public(d) for d in docs]


async def _get_period(db, workspace_id, company_id, period_id):
    p = await db.financial_periods.find_one(
        {"_id": period_id, "workspace_id": workspace_id, "company_id": company_id})
    if not p:
        raise HTTPException(status_code=404, detail="Période introuvable")
    return p


async def transition_period(db, workspace_id, company_id, user, period_id, target):
    """Canonical period state machine (single source of truth = financial_periods).
    ``closed`` is terminal — reopening is permanently forbidden for everyone."""
    if target not in PERIOD_STATUSES:
        raise HTTPException(status_code=422, detail="Statut de période invalide")
    p = await _get_period(db, workspace_id, company_id, period_id)
    cur = p.get("status", "open")
    if cur == target:
        return _period_public(p)
    if cur == "closed":
        raise HTTPException(
            status_code=409,
            detail="Période clôturée : réouverture définitivement interdite. Corrigez via une écriture dans une période ultérieure.")
    if target not in _ALLOWED_TRANSITIONS.get(cur, set()):
        raise HTTPException(status_code=409, detail=f"Transition de période interdite : {cur} → {target}")
    await db.financial_periods.update_one(
        {"_id": period_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": {"status": target, "updated_at": _now(), "updated_by": user.get("id")}})
    p["status"] = target
    return _period_public(p)


async def _assert_postable_period(db, workspace_id, company_id, period):
    """Posting is allowed only into an OPEN period, and only if every EARLIER
    period (by start_date) is already closed (sequential posting)."""
    st = period.get("status", "open")
    if st == "locked":
        raise HTTPException(status_code=409, detail="Période verrouillée : aucune comptabilisation permise.")
    if st == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : aucune comptabilisation permise.")
    earlier_open = await db.financial_periods.find_one({
        "workspace_id": workspace_id, "company_id": company_id,
        "start_date": {"$lt": period.get("start_date")}, "status": {"$ne": "closed"}})
    if earlier_open:
        raise HTTPException(
            status_code=409,
            detail="Une période antérieure n'est pas clôturée : comptabilisation impossible dans une période ultérieure.")


# --------------------------------------------------------------------------- #
# Entries — accounting_entries (workflow document, NOT the ledger)
# --------------------------------------------------------------------------- #
def _validate_lines(lines):
    if not lines or len(lines) < 2:
        raise HTTPException(status_code=422, detail="Une écriture requiert au moins deux lignes.")
    td = tc = 0.0
    clean = []
    for ln in lines:
        d = _money(ln.get("debit"))
        c = _money(ln.get("credit"))
        if d < 0 or c < 0:
            raise HTTPException(status_code=422, detail="Montants négatifs interdits.")
        if (d > 0 and c > 0) or (d == 0 and c == 0):
            raise HTTPException(status_code=422, detail="Chaque ligne doit être soit un débit, soit un crédit.")
        if not ln.get("account"):
            raise HTTPException(status_code=422, detail="Compte requis sur chaque ligne.")
        td += d
        tc += c
        clean.append({"account": str(ln.get("account")), "description": ln.get("description", ""),
                      "debit": d, "credit": c})
    td, tc = round(td, 2), round(tc, 2)
    if td != tc:
        raise HTTPException(status_code=422, detail=f"Écriture déséquilibrée : débits {td} ≠ crédits {tc}.")
    if td == 0:
        raise HTTPException(status_code=422, detail="Écriture vide.")
    return clean, td, tc


def _audit(action, user, frm, to):
    return {"action": action, "by": user.get("id"), "by_email": user.get("email"),
            "at": _now(), "from_status": frm, "to_status": to}


async def list_entries(db, workspace_id, company_id, *, status=None, period_id=None):
    q = {"workspace_id": workspace_id, "company_id": company_id}
    if status:
        q["status"] = status
    if period_id:
        q["period_id"] = period_id
    docs = await db.accounting_entries.find(q).sort("created_at", -1).to_list(500)
    return [public_entry(d) for d in docs]


async def get_entry(db, workspace_id, company_id, entry_id):
    d = await db.accounting_entries.find_one(
        {"_id": entry_id, "workspace_id": workspace_id, "company_id": company_id})
    if not d:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    return d


async def create_entry(db, workspace_id, company_id, user, payload):
    period = await _get_period(db, workspace_id, company_id, payload.get("period_id"))
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : création d'écriture impossible.")
    lines, td, tc = _validate_lines(payload.get("lines"))
    doc = {"_id": f"ace_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "period_id": period["_id"], "financial_period_id": period["_id"],
           "financial_year_id": period.get("financial_year_id"),
           "date": payload.get("date") or _now()[:10],
           "memo": payload.get("memo", ""), "reference": payload.get("reference", ""),
           "source": payload.get("source") or "manual", "status": "draft",
           "lines": lines, "total_debit": td, "total_credit": tc,
           "created_by": user.get("id"), "created_at": _now(),
           "attachments": [], "audit": [_audit("create", user, None, "draft")]}
    await db.accounting_entries.insert_one(doc)
    return public_entry(doc)


async def update_draft(db, workspace_id, company_id, user, entry_id, payload):
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") != "draft":
        raise HTTPException(status_code=409, detail="Seuls les brouillons sont modifiables.")
    changes = {}
    if payload.get("lines") is not None:
        lines, td, tc = _validate_lines(payload["lines"])
        changes.update({"lines": lines, "total_debit": td, "total_credit": tc})
    for f in ("memo", "reference", "date", "source"):
        if payload.get(f) is not None:
            changes[f] = payload[f]
    if payload.get("period_id") and payload["period_id"] != d["period_id"]:
        period = await _get_period(db, workspace_id, company_id, payload["period_id"])
        if period.get("status") == "closed":
            raise HTTPException(status_code=409, detail="Période clôturée.")
        changes["period_id"] = period["_id"]
        changes["financial_period_id"] = period["_id"]
        changes["financial_year_id"] = period.get("financial_year_id")
    if changes:
        await db.accounting_entries.update_one(
            {"_id": entry_id}, {"$set": changes, "$push": {"audit": _audit("update", user, "draft", "draft")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def _require_status(db, workspace_id, company_id, entry_id, expected_from):
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") != expected_from:
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut actuel « {d.get('status')} ».")
    return d


async def submit_entry(db, workspace_id, company_id, user, entry_id):
    d = await _require_status(db, workspace_id, company_id, entry_id, "draft")
    _validate_lines(d.get("lines"))
    await db.accounting_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _audit("submit", user, "draft", "submitted")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def approve_entry(db, workspace_id, company_id, user, entry_id):
    """Requires accounting.entry_approve (enforced at route) + MAKER-CHECKER:
    the creator can never approve their own entry, regardless of role."""
    d = await _require_status(db, workspace_id, company_id, entry_id, "submitted")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403,
                            detail="Séparation des tâches : le créateur d'une écriture ne peut pas l'approuver.")
    await db.accounting_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "approved", "approved_by": user.get("id")},
        "$push": {"audit": _audit("approve", user, "submitted", "approved")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def post_entry(db, workspace_id, company_id, user, entry_id):
    """Requires accounting.entry_post (enforced at route). Creates EXACTLY ONE
    canonical journal entry (P2.6) and links it immutably. Idempotent: a retry on
    an already-posted entry returns it without creating a second journal entry."""
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") == "posted" and d.get("journal_entry_id"):
        return public_entry(d)  # idempotent — no duplicate ledger write
    if d.get("status") != "approved":
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut actuel « {d.get('status')} ».")
    period = await _get_period(db, workspace_id, company_id, d["period_id"])
    await _assert_postable_period(db, workspace_id, company_id, period)
    _validate_lines(d.get("lines"))
    je = await journal_service.create_workflow_journal_entry(
        db, workspace_id, company_id, user,
        financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=d.get("date"), reference=d.get("reference") or "", description=d.get("memo") or "",
        lines=d.get("lines", []), external_id=entry_id, source_type="manual")
    await db.accounting_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "posted", "posted_by": user.get("id"), "posted_at": _now(),
                 "journal_entry_id": je["_id"]},
        "$push": {"audit": _audit("post", user, "approved", "posted")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def reverse_entry(db, workspace_id, company_id, user, entry_id, *, target_period_id=None, memo=None):
    """Requires accounting.entry_reverse (enforced at route). Creates a NEW mirror
    accounting_entry (posted) AND a NEW canonical journal entry linked to the
    original journal entry. The original ledger entry is never mutated (only a
    non-financial back-reference link is added)."""
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") != "posted":
        raise HTTPException(status_code=409, detail="Seules les écritures comptabilisées peuvent être extournées.")
    orig_je_id = d.get("journal_entry_id")
    tgt_id = target_period_id or d["period_id"]
    period = await _get_period(db, workspace_id, company_id, tgt_id)
    await _assert_postable_period(db, workspace_id, company_id, period)
    rev_lines = [{"account": ln["account"], "description": f"Extourne — {ln.get('description', '')}".strip(),
                  "debit": ln.get("credit", 0), "credit": ln.get("debit", 0)} for ln in d.get("lines", [])]
    lines, td, tc = _validate_lines(rev_lines)
    rev_id = f"ace_{uuid.uuid4().hex}"
    ref = f"REV-{d.get('reference') or entry_id}"
    rev_memo = memo or f"Extourne de {d.get('reference') or entry_id}"
    # 1) canonical journal entry for the reversal, linked to the original ledger entry.
    rev_je = await journal_service.create_workflow_journal_entry(
        db, workspace_id, company_id, user,
        financial_year_id=period.get("financial_year_id"), financial_period_id=period["_id"],
        entry_date=_now()[:10], reference=ref, description=rev_memo,
        lines=lines, external_id=rev_id, source_type="manual",
        reverses_journal_entry_id=orig_je_id)
    # 2) reversal accounting_entry (workflow document).
    rev = {"_id": rev_id, "workspace_id": workspace_id, "company_id": company_id,
           "period_id": period["_id"], "financial_period_id": period["_id"],
           "financial_year_id": period.get("financial_year_id"), "date": _now()[:10],
           "memo": rev_memo, "reference": ref, "source": "reversal", "status": "posted",
           "lines": lines, "total_debit": td, "total_credit": tc,
           "created_by": user.get("id"), "created_at": _now(),
           "posted_by": user.get("id"), "posted_at": _now(),
           "reversal_of": entry_id, "journal_entry_id": rev_je["_id"],
           "attachments": [], "audit": [_audit("create_reversal", user, None, "posted")]}
    await db.accounting_entries.insert_one(rev)
    # 3) mark the original workflow document reversed + back-reference on the ledger.
    await db.accounting_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "reversed", "reversed_by": user.get("id"),
                 "reversed_by_entry": rev_id, "reversal_journal_entry_id": rev_je["_id"]},
        "$push": {"audit": _audit("reverse", user, "posted", "reversed")}})
    if orig_je_id:
        await journal_service.link_reversal(db, workspace_id, company_id, orig_je_id, rev_je["_id"])
    return public_entry(rev)


async def add_attachment(db, workspace_id, company_id, user, entry_id, *, name, content_type, size, storage_key):
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") in ("posted", "reversed"):
        raise HTTPException(status_code=409, detail="Écriture comptabilisée : pièces jointes verrouillées.")
    att = {"id": f"att_{uuid.uuid4().hex}", "name": name, "content_type": content_type,
           "size": size, "storage_key": storage_key, "uploaded_by": user.get("id"), "at": _now()}
    await db.accounting_entries.update_one(
        {"_id": entry_id},
        {"$push": {"attachments": att, "audit": _audit("attach", user, d.get("status"), d.get("status"))}})
    return att
