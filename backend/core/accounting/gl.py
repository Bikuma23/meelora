"""ACCOUNTING A2 — Core GL & posting workflow.

ISOLATED module: uses dedicated collections `gl_periods` / `gl_entries` and never
touches legacy financial data (qc9434_*, acct_*, trial_balance_*) or any legacy
calculation. Authorization for sensitive transitions is delegated to the caller
(routes) via `require_sensitive_permission`; this layer only enforces GL business
rules (balanced entries, lifecycle, period locking, sequential posting,
maker-checker) and writes a full audit trail.

Entry lifecycle:   draft -> submitted -> approved -> posted -> reversed
Period lifecycle:  open -> locked -> closed   (locked <-> open allowed; closed is
                   TERMINAL — reopening is permanently forbidden for everyone).
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

ENTRY_STATUSES = ("draft", "submitted", "approved", "posted", "reversed")
PERIOD_STATUSES = ("open", "locked", "closed")
# Allowed period transitions (A2). closed is terminal — no reopen, no re-lock.
_PERIOD_TRANSITIONS = {
    ("open", "locked"), ("open", "closed"),
    ("locked", "closed"), ("locked", "open"),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Montant invalide")


def public_period(d: dict) -> dict:
    return {
        "id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
        "code": d.get("code"), "label": d.get("label"), "sequence": d.get("sequence"),
        "status": d.get("status", "open"), "created_at": d.get("created_at"),
        "transitions": d.get("transitions", []),
    }


def public_entry(d: dict) -> dict:
    return {
        "id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
        "period_id": d.get("period_id"), "date": d.get("date"), "memo": d.get("memo"),
        "reference": d.get("reference"), "source": d.get("source", "manual"),
        "status": d.get("status", "draft"), "lines": d.get("lines", []),
        "total_debit": d.get("total_debit"), "total_credit": d.get("total_credit"),
        "created_by": d.get("created_by"), "created_at": d.get("created_at"),
        "submitted_by": d.get("submitted_by"), "approved_by": d.get("approved_by"),
        "posted_by": d.get("posted_by"), "reversed_by": d.get("reversed_by"),
        "reversal_of": d.get("reversal_of"), "reversed_by_entry": d.get("reversed_by_entry"),
        "attachments": d.get("attachments", []), "audit": d.get("audit", []),
    }


# --------------------------------------------------------------------------- #
# Periods
# --------------------------------------------------------------------------- #
async def list_periods(db, workspace_id, company_id):
    docs = await db.gl_periods.find({"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    docs.sort(key=lambda d: d.get("sequence", 0))
    return [public_period(d) for d in docs]


async def create_period(db, workspace_id, company_id, user, *, code, label=None):
    if not code:
        raise HTTPException(status_code=422, detail="Code de période requis")
    if await db.gl_periods.find_one({"workspace_id": workspace_id, "company_id": company_id, "code": code}):
        raise HTTPException(status_code=409, detail="Période déjà existante")
    seq = await db.gl_periods.count_documents({"workspace_id": workspace_id, "company_id": company_id})
    doc = {"_id": f"glp_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "code": code, "label": label or code, "sequence": seq, "status": "open",
           "created_at": _now(), "created_by": user.get("id"), "transitions": []}
    await db.gl_periods.insert_one(doc)
    return public_period(doc)


async def _get_period(db, workspace_id, company_id, period_id):
    p = await db.gl_periods.find_one({"_id": period_id, "workspace_id": workspace_id, "company_id": company_id})
    if not p:
        raise HTTPException(status_code=404, detail="Période introuvable")
    return p


async def transition_period(db, workspace_id, company_id, user, period_id, target):
    if target not in PERIOD_STATUSES:
        raise HTTPException(status_code=422, detail="Statut de période invalide")
    p = await _get_period(db, workspace_id, company_id, period_id)
    cur = p.get("status", "open")
    if cur == target:
        return public_period(p)
    if cur == "closed":
        # Terminal — reopening / re-locking a closed period is permanently forbidden.
        raise HTTPException(status_code=409,
                            detail="Période clôturée : réouverture définitivement interdite. Corrigez via une écriture dans une période ultérieure.")
    if (cur, target) not in _PERIOD_TRANSITIONS:
        raise HTTPException(status_code=409, detail=f"Transition de période interdite : {cur} → {target}")
    entry = {"from": cur, "to": target, "by": user.get("id"), "by_email": user.get("email"), "at": _now()}
    await db.gl_periods.update_one({"_id": period_id},
                                   {"$set": {"status": target}, "$push": {"transitions": entry}})
    p["status"] = target
    p.setdefault("transitions", []).append(entry)
    return public_period(p)


async def _assert_postable_period(db, workspace_id, company_id, period):
    """Posting is allowed only into an OPEN period, and only if every EARLIER
    period is already closed (sequential posting)."""
    if period.get("status") == "locked":
        raise HTTPException(status_code=409, detail="Période verrouillée : aucune comptabilisation permise.")
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : aucune comptabilisation permise.")
    earlier_open = await db.gl_periods.find_one({
        "workspace_id": workspace_id, "company_id": company_id,
        "sequence": {"$lt": period.get("sequence", 0)}, "status": {"$ne": "closed"}})
    if earlier_open:
        raise HTTPException(status_code=409,
                            detail="Une période antérieure n'est pas clôturée : comptabilisation impossible dans une période ultérieure.")


# --------------------------------------------------------------------------- #
# Entries
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
    docs = await db.gl_entries.find(q).sort("created_at", -1).to_list(500)
    return [public_entry(d) for d in docs]


async def get_entry(db, workspace_id, company_id, entry_id):
    d = await db.gl_entries.find_one({"_id": entry_id, "workspace_id": workspace_id, "company_id": company_id})
    if not d:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    return d


async def create_entry(db, workspace_id, company_id, user, payload):
    period = await _get_period(db, workspace_id, company_id, payload.get("period_id"))
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : création d'écriture impossible.")
    lines, td, tc = _validate_lines(payload.get("lines"))
    doc = {"_id": f"gle_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "period_id": period["_id"], "date": payload.get("date") or _now()[:10],
           "memo": payload.get("memo", ""), "reference": payload.get("reference", ""),
           "source": payload.get("source") or "manual", "status": "draft",
           "lines": lines, "total_debit": td, "total_credit": tc,
           "created_by": user.get("id"), "created_at": _now(),
           "attachments": [], "audit": [_audit("create", user, None, "draft")]}
    await db.gl_entries.insert_one(doc)
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
    if changes:
        await db.gl_entries.update_one({"_id": entry_id}, {"$set": changes, "$push": {"audit": _audit("update", user, "draft", "draft")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def _transition_entry(db, workspace_id, company_id, user, entry_id, action, expected_from, to, extra=None):
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") != expected_from:
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut actuel « {d.get('status')} ».")
    return d


async def submit_entry(db, workspace_id, company_id, user, entry_id):
    d = await _transition_entry(db, workspace_id, company_id, user, entry_id, "submit", "draft", "submitted")
    _validate_lines(d.get("lines"))
    await db.gl_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _audit("submit", user, "draft", "submitted")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def approve_entry(db, workspace_id, company_id, user, entry_id):
    """Requires accounting.entry_approve (enforced at route) + MAKER-CHECKER:
    the creator can never approve their own entry, regardless of role."""
    d = await _transition_entry(db, workspace_id, company_id, user, entry_id, "approve", "submitted", "approved")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403,
                            detail="Séparation des tâches : le créateur d'une écriture ne peut pas l'approuver.")
    await db.gl_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "approved", "approved_by": user.get("id")},
        "$push": {"audit": _audit("approve", user, "submitted", "approved")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def post_entry(db, workspace_id, company_id, user, entry_id):
    """Requires accounting.entry_post (enforced at route). Period must be open and
    all earlier periods closed (sequential posting)."""
    d = await _transition_entry(db, workspace_id, company_id, user, entry_id, "post", "approved", "posted")
    period = await _get_period(db, workspace_id, company_id, d["period_id"])
    await _assert_postable_period(db, workspace_id, company_id, period)
    _validate_lines(d.get("lines"))
    await db.gl_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "posted", "posted_by": user.get("id"), "posted_at": _now()},
        "$push": {"audit": _audit("post", user, "approved", "posted")}})
    return public_entry(await get_entry(db, workspace_id, company_id, entry_id))


async def reverse_entry(db, workspace_id, company_id, user, entry_id, *, target_period_id=None, memo=None):
    """Requires accounting.entry_reverse (enforced at route). Creates a mirror
    POSTED entry in a postable period; the original is marked reversed. Never
    reopens or mutates a closed period."""
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") != "posted":
        raise HTTPException(status_code=409, detail="Seules les écritures comptabilisées peuvent être extournées.")
    tgt_id = target_period_id or d["period_id"]
    period = await _get_period(db, workspace_id, company_id, tgt_id)
    await _assert_postable_period(db, workspace_id, company_id, period)
    rev_lines = [{"account": ln["account"], "description": f"Extourne — {ln.get('description', '')}".strip(),
                  "debit": ln.get("credit", 0), "credit": ln.get("debit", 0)} for ln in d.get("lines", [])]
    lines, td, tc = _validate_lines(rev_lines)
    rev = {"_id": f"gle_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "period_id": period["_id"], "date": _now()[:10],
           "memo": memo or f"Extourne de {d.get('reference') or entry_id}",
           "reference": f"REV-{d.get('reference') or entry_id}", "source": "reversal",
           "status": "posted", "lines": lines, "total_debit": td, "total_credit": tc,
           "created_by": user.get("id"), "created_at": _now(), "posted_by": user.get("id"), "posted_at": _now(),
           "reversal_of": entry_id, "attachments": [],
           "audit": [_audit("create_reversal", user, None, "posted")]}
    await db.gl_entries.insert_one(rev)
    await db.gl_entries.update_one({"_id": entry_id}, {
        "$set": {"status": "reversed", "reversed_by": user.get("id"), "reversed_by_entry": rev["_id"]},
        "$push": {"audit": _audit("reverse", user, "posted", "reversed")}})
    return public_entry(rev)


async def add_attachment(db, workspace_id, company_id, user, entry_id, *, name, content_type, size, storage_key):
    d = await get_entry(db, workspace_id, company_id, entry_id)
    if d.get("status") in ("posted", "reversed"):
        raise HTTPException(status_code=409, detail="Écriture comptabilisée : pièces jointes verrouillées.")
    att = {"id": f"att_{uuid.uuid4().hex}", "name": name, "content_type": content_type,
           "size": size, "storage_key": storage_key, "uploaded_by": user.get("id"), "at": _now()}
    await db.gl_entries.update_one({"_id": entry_id}, {"$push": {"attachments": att, "audit": _audit("attach", user, d.get("status"), d.get("status"))}})
    return att
