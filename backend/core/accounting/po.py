"""A4.5 — Purchase Orders + 2-way matching. Financial control on AP; NOT procurement.
Builds on A4.1 (suppliers), A4.2 (canonical AP invoices), A4.4 (hints only), P2.

Adjustments applied per GATE A4.5:
  - Two independent status dimensions: `po_status` and `invoicing_status`.
  - `closed` is EXPLICIT, never auto-triggered by fully_invoiced.
  - Cancellation forbidden once any invoice is linked.
  - `accounting.po_match_override` is sensitive; it may accept a tolerance/mismatch
    exception WITH reason+audit, but NEVER silently bypasses real over-invoicing —
    over-invoicing requires a PO amendment + re-approval.
  - Tolerance presets Strict / Standard / Personnalisé; Standard = CHF 1.00 abs, 0% price/pct, 0 qty.
  - Matching policy is versioned/snapshotted on each invoice match.
  - No parallel GL: a PO never posts; only the A4.2 invoice posts (canonical P2).
"""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException

from . import ap as _ap  # reuse suppliers/invoices/fx/period helpers (no duplication)

_money = _ap._money
_now = _ap._now


def _audit(action, user, frm, to, extra=None):
    a = {"action": action, "by": (user or {}).get("id"), "by_email": (user or {}).get("email"),
         "from": frm, "to": to, "at": _now()}
    if extra:
        a.update(extra)
    return a


# --------------------------------------------------------------------------- #
# Company AP settings — approval matrix + match tolerance (versioned)
# --------------------------------------------------------------------------- #
_DEFAULT_MATRIX = {"matrix_version": 1, "currency_basis": "functional",
                   "rules": [{"max_amount": None, "levels": ["finance"]}]}
# Conservative Standard preset (GATE): CHF 1.00 absolute only.
_TOLERANCE_PRESETS = {
    "strict": {"amount_abs": 0.0, "amount_pct": 0.0, "price_pct": 0.0, "qty_abs": 0.0},
    "standard": {"amount_abs": 1.0, "amount_pct": 0.0, "price_pct": 0.0, "qty_abs": 0.0},
}


async def get_ap_settings(db, ws, co):
    s = await db.company_ap_settings.find_one({"workspace_id": ws, "company_id": co})
    if not s:
        s = {"workspace_id": ws, "company_id": co, "po_approval_matrix": _DEFAULT_MATRIX,
             "match_tolerance": {"policy_version": 1, "preset": "standard", **_TOLERANCE_PRESETS["standard"]}}
    else:
        s.setdefault("po_approval_matrix", _DEFAULT_MATRIX)
        s.setdefault("match_tolerance", {"policy_version": 1, "preset": "standard", **_TOLERANCE_PRESETS["standard"]})
    return {"po_approval_matrix": s["po_approval_matrix"], "match_tolerance": s["match_tolerance"]}


async def set_ap_settings(db, ws, co, user, payload):
    cur = await get_ap_settings(db, ws, co)
    upd = {"workspace_id": ws, "company_id": co, "updated_at": _now()}
    if payload.get("po_approval_matrix") is not None:
        m = payload["po_approval_matrix"]
        m["matrix_version"] = int(cur["po_approval_matrix"].get("matrix_version", 1)) + 1
        upd["po_approval_matrix"] = m
    if payload.get("match_tolerance") is not None:
        t = payload["match_tolerance"]
        preset = t.get("preset", "standard")
        base = _TOLERANCE_PRESETS.get(preset, {})
        merged = {**base, **{k: t[k] for k in ("amount_abs", "amount_pct", "price_pct", "qty_abs") if k in t}}
        merged["preset"] = preset
        merged["policy_version"] = int(cur["match_tolerance"].get("policy_version", 1)) + 1
        upd["match_tolerance"] = merged
    await db.company_ap_settings.update_one({"workspace_id": ws, "company_id": co}, {"$set": upd}, upsert=True)
    return await get_ap_settings(db, ws, co)


def required_levels(matrix, amount_functional):
    for rule in matrix.get("rules", []):
        mx = rule.get("max_amount")
        if mx is None or amount_functional <= mx:
            return rule.get("levels", [])
    return matrix.get("rules", [{}])[-1].get("levels", [])


# --------------------------------------------------------------------------- #
# PO object + lifecycle (po_status ⟂ invoicing_status)
# --------------------------------------------------------------------------- #
_PO_STATUS = ("draft", "submitted", "approved", "rejected", "sent", "cancelled", "closed")
_INV_STATUS = ("not_invoiced", "partially_invoiced", "fully_invoiced")


def public_po(d):
    if not d:
        return None
    return {"id": d.get("_id"), "number": d.get("number"), "supplier_id": d.get("supplier_id"),
            "supplier_name": d.get("supplier_name_snapshot"), "po_date": d.get("po_date"),
            "requested_by": d.get("requested_by"), "po_owner_id": d.get("po_owner_id"),
            "currency": d.get("currency"), "fx": d.get("fx"), "po_status": d.get("po_status", "draft"),
            "invoicing_status": d.get("invoicing_status", "not_invoiced"),
            "lines": d.get("lines") or [], "subtotal": d.get("subtotal"), "tax_total": d.get("tax_total"),
            "total": d.get("total"), "note": d.get("note"), "reference": d.get("reference"),
            "attachments": d.get("attachments") or [], "approvers": d.get("approvers") or [],
            "approval_snapshot": d.get("approval_snapshot"), "linked_invoice_ids": d.get("linked_invoice_ids") or [],
            "invoiced_total": d.get("invoiced_total", 0.0), "remaining_amount": d.get("remaining_amount", d.get("total", 0.0)),
            "created_by": d.get("created_by"), "created_at": d.get("created_at"), "audit": d.get("audit", [])}


async def get_po(db, ws, co, pid):
    d = await db.ap_purchase_orders.find_one({"_id": pid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Bon de commande introuvable")
    return d


async def list_pos(db, ws, co, *, po_status=None, supplier_id=None):
    q = {"workspace_id": ws, "company_id": co}
    if po_status:
        q["po_status"] = po_status
    if supplier_id:
        q["supplier_id"] = supplier_id
    docs = await db.ap_purchase_orders.find(q).sort("created_at", -1).to_list(2000)
    return [public_po(d) for d in docs]


async def create_po(db, ws, co, user, payload):
    supplier = await _ap.get_supplier(db, ws, co, payload["supplier_id"])
    functional = await _ap._functional_currency(db, ws, co)
    currency = (payload.get("currency") or supplier.get("default_currency") or functional).upper()
    po_date = payload.get("po_date") or _now()[:10]
    fx = await _ap._resolve_fx(db, ws, co, currency, functional, po_date, payload.get("fx_rate"))
    mapping = await _ap.get_ap_mapping(db, ws, co)
    raw, subtotal, tax_total, total = await _ap._compute_ap_lines(
        db, ws, co, payload.get("lines") or [], po_date, mapping["default_expense_account_code"])
    lines = [{**ln, "line_id": f"pol_{uuid.uuid4().hex}", "invoiced_qty": 0.0, "invoiced_net": 0.0} for ln in raw]
    doc = {"_id": f"po_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
           "number": None, "supplier_id": supplier["_id"], "supplier_name_snapshot": supplier.get("name"),
           "po_date": po_date, "requested_by": user.get("id"), "po_owner_id": payload.get("po_owner_id") or user.get("id"),
           "currency": currency, "fx": fx, "po_status": "draft", "invoicing_status": "not_invoiced",
           "lines": lines, "subtotal": subtotal, "tax_total": tax_total, "total": total,
           "note": payload.get("note"), "reference": payload.get("reference"), "attachments": [],
           "approvers": [], "approval_snapshot": None, "linked_invoice_ids": [], "invoiced_total": 0.0,
           "remaining_amount": total, "created_by": user.get("id"), "created_at": _now(),
           "audit": [_audit("create", user, None, "draft")]}
    await db.ap_purchase_orders.insert_one(doc)
    return public_po(doc)


async def update_po(db, ws, co, user, pid, payload):
    d = await get_po(db, ws, co, pid)
    if d.get("linked_invoice_ids"):
        raise HTTPException(status_code=409, detail="PO déjà utilisé par une facture : modification via amendement/ré-approbation uniquement.")
    if d.get("po_status") not in ("draft", "submitted"):
        raise HTTPException(status_code=409, detail="Seul un PO en brouillon/soumis peut être modifié.")
    return await create_po_update(db, ws, co, user, d, payload)


async def create_po_update(db, ws, co, user, d, payload):
    # In-place edit of a non-linked draft/submitted PO (recompute totals).
    changes = {}
    for f in ("note", "reference", "po_owner_id"):
        if payload.get(f) is not None:
            changes[f] = payload[f]
    if payload.get("lines") is not None:
        mapping = await _ap.get_ap_mapping(db, ws, co)
        raw, subtotal, tax_total, total = await _ap._compute_ap_lines(
            db, ws, co, payload["lines"], d.get("po_date"), mapping["default_expense_account_code"])
        lines = [{**ln, "line_id": (payload["lines"][i].get("line_id") if i < len(payload["lines"]) else None) or f"pol_{uuid.uuid4().hex}",
                  "invoiced_qty": 0.0, "invoiced_net": 0.0} for i, ln in enumerate(raw)]
        changes.update({"lines": lines, "subtotal": subtotal, "tax_total": tax_total,
                        "total": total, "remaining_amount": total})
    if changes:
        await db.ap_purchase_orders.update_one({"_id": d["_id"]}, {"$set": changes,
            "$push": {"audit": _audit("update", user, d.get("po_status"), d.get("po_status"))}})
    return public_po(await get_po(db, ws, co, d["_id"]))


async def submit_po(db, ws, co, user, pid):
    d = await get_po(db, ws, co, pid)
    if d.get("po_status") != "draft":
        raise HTTPException(status_code=409, detail="Seul un PO brouillon peut être soumis.")
    await db.ap_purchase_orders.update_one({"_id": pid}, {"$set": {"po_status": "submitted"},
        "$push": {"audit": _audit("submit", user, "draft", "submitted")}})
    return public_po(await get_po(db, ws, co, pid))


async def approve_po(db, ws, co, user, pid):
    d = await get_po(db, ws, co, pid)
    if d.get("po_status") != "submitted":
        raise HTTPException(status_code=409, detail="Seul un PO soumis peut être approuvé.")
    if d.get("requested_by") == user.get("id") or d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403, detail="Séparation des tâches : le demandeur/créateur ne peut pas approuver le PO.")
    settings = await get_ap_settings(db, ws, co)
    amount_func = _ap.fx_service.convert(d["total"], (d.get("fx") or {}).get("rate", 1.0))
    levels = required_levels(settings["po_approval_matrix"], amount_func)
    snap = {"matrix_version": settings["po_approval_matrix"].get("matrix_version"), "required_levels": levels,
            "amount_functional": _money(amount_func)}
    year = _now()[:4]
    seq = await db.ap_purchase_orders.count_documents({"workspace_id": ws, "company_id": co, "number": {"$ne": None}}) + 1
    number = d.get("number") or f"PO-{year}-{seq:04d}"
    await db.ap_purchase_orders.update_one({"_id": pid}, {
        "$set": {"po_status": "approved", "approval_snapshot": snap, "number": number},
        "$push": {"approvers": {"user_id": user.get("id"), "decided": "approved", "at": _now()},
                  "audit": _audit("approve", user, "submitted", "approved", {"levels": levels})}})
    return public_po(await get_po(db, ws, co, pid))


async def reject_po(db, ws, co, user, pid, reason=None):
    d = await get_po(db, ws, co, pid)
    if d.get("po_status") != "submitted":
        raise HTTPException(status_code=409, detail="Seul un PO soumis peut être rejeté.")
    await db.ap_purchase_orders.update_one({"_id": pid}, {"$set": {"po_status": "rejected"},
        "$push": {"approvers": {"user_id": user.get("id"), "decided": "rejected", "at": _now(), "reason": reason},
                  "audit": _audit("reject", user, "submitted", "rejected", {"reason": reason})}})
    return public_po(await get_po(db, ws, co, pid))


async def send_po(db, ws, co, user, pid):
    d = await get_po(db, ws, co, pid)
    if d.get("po_status") != "approved":
        raise HTTPException(status_code=409, detail="Seul un PO approuvé peut être envoyé.")
    await db.ap_purchase_orders.update_one({"_id": pid}, {"$set": {"po_status": "sent"},
        "$push": {"audit": _audit("send", user, "approved", "sent")}})
    return public_po(await get_po(db, ws, co, pid))


async def cancel_po(db, ws, co, user, pid):
    d = await get_po(db, ws, co, pid)
    if d.get("linked_invoice_ids"):
        raise HTTPException(status_code=409, detail="Annulation interdite : le PO a des factures liées.")
    if d.get("po_status") in ("closed", "cancelled", "rejected"):
        raise HTTPException(status_code=409, detail="PO déjà terminal.")
    await db.ap_purchase_orders.update_one({"_id": pid}, {"$set": {"po_status": "cancelled"},
        "$push": {"audit": _audit("cancel", user, d.get("po_status"), "cancelled")}})
    return public_po(await get_po(db, ws, co, pid))


async def close_po(db, ws, co, user, pid):
    """Explicit close — NEVER auto-triggered by fully_invoiced."""
    d = await get_po(db, ws, co, pid)
    if d.get("po_status") in ("closed", "cancelled", "rejected", "draft"):
        raise HTTPException(status_code=409, detail="PO non fermable dans cet état.")
    await db.ap_purchase_orders.update_one({"_id": pid}, {"$set": {"po_status": "closed"},
        "$push": {"audit": _audit("close", user, d.get("po_status"), "closed")}})
    return public_po(await get_po(db, ws, co, pid))


# --------------------------------------------------------------------------- #
# Matching 2-way (deterministic authority)
# --------------------------------------------------------------------------- #
def _within_tol(variance_abs, base, tol):
    if variance_abs <= float(tol.get("amount_abs", 0)) + 1e-6:
        return True
    pct = float(tol.get("amount_pct", 0))
    return pct > 0 and base > 0 and (variance_abs / base * 100.0) <= pct + 1e-9


async def _recompute_po_invoicing(db, ws, co, po_id):
    po = await get_po(db, ws, co, po_id)
    invoiced = 0.0
    for iid in po.get("linked_invoice_ids") or []:
        inv = await db.ap_invoices.find_one({"_id": iid, "workspace_id": ws, "company_id": co})
        if inv and inv.get("document_status") != "rejected":
            invoiced += float(inv.get("total") or 0)
    invoiced = _money(invoiced)
    total = float(po.get("total") or 0)
    tol = (await get_ap_settings(db, ws, co))["match_tolerance"]
    if invoiced <= 0.001:
        st = "not_invoiced"
    elif invoiced >= total - float(tol.get("amount_abs", 0)) - 1e-6:
        st = "fully_invoiced"
    else:
        st = "partially_invoiced"
    await db.ap_purchase_orders.update_one({"_id": po_id}, {"$set": {
        "invoiced_total": invoiced, "remaining_amount": _money(max(total - invoiced, 0.0)),
        "invoicing_status": st}})
    return st


async def compute_matching(db, ws, co, po, invoice):
    tol = (await get_ap_settings(db, ws, co))["match_tolerance"]
    supplier_ok = po.get("supplier_id") == invoice.get("supplier_id")
    currency_ok = (po.get("currency") or "").upper() == (invoice.get("currency") or "").upper()
    already = 0.0
    for iid in po.get("linked_invoice_ids") or []:
        if iid == invoice.get("_id"):
            continue
        prev = await db.ap_invoices.find_one({"_id": iid, "workspace_id": ws, "company_id": co})
        if prev and prev.get("document_status") != "rejected":
            already += float(prev.get("total") or 0)
    inv_total = float(invoice.get("total") or 0)
    cumulative = _money(already + inv_total)
    over = _money(cumulative - float(po.get("total") or 0))
    checks = [
        {"name": "supplier", "ok": supplier_ok, "po_value": po.get("supplier_name_snapshot"), "invoice_value": invoice.get("supplier_id")},
        {"name": "currency", "ok": currency_ok, "po_value": po.get("currency"), "invoice_value": invoice.get("currency")},
        {"name": "total", "ok": over <= float(tol.get("amount_abs", 0)) + 1e-6, "po_value": po.get("total"), "invoice_value": inv_total},
    ]
    if not supplier_ok or not currency_ok:
        status, kind = "exception", "mismatch"
    elif over > float(tol.get("amount_abs", 0)) + 1e-6 and not _within_tol(over, float(po.get("total") or 0), tol):
        status, kind = "exception", "over_invoicing"
    elif over > 1e-6:
        status, kind = "within_tolerance", "tolerance"
    else:
        status, kind = "matched", None
    return {"status": status, "exception_kind": kind, "checks": checks, "variance": over,
            "cumulative_invoiced": cumulative, "po_total": po.get("total"),
            "policy_version": tol.get("policy_version"), "overridden": False, "matched_at": _now()}


async def _apply_match_to_invoice(db, ws, co, invoice_id, po_id, result):
    await db.ap_invoices.update_one({"_id": invoice_id, "workspace_id": ws, "company_id": co},
        {"$set": {"purchase_order_id": po_id, "matching_status": result["status"], "matching_result": result}})


async def link_invoice(db, ws, co, user, invoice_id, po_id):
    inv = await _ap.get_invoice(db, ws, co, invoice_id)
    po = await get_po(db, ws, co, po_id)
    if po.get("po_status") not in ("approved", "sent", "partially_invoiced"):
        # allow linking on approved/sent PO
        if po.get("po_status") not in ("approved", "sent"):
            raise HTTPException(status_code=409, detail="Le PO doit être approuvé/envoyé pour être lié.")
    result = await compute_matching(db, ws, co, po, inv)
    await _apply_match_to_invoice(db, ws, co, invoice_id, po_id, result)
    if invoice_id not in (po.get("linked_invoice_ids") or []):
        await db.ap_purchase_orders.update_one({"_id": po_id}, {
            "$addToSet": {"linked_invoice_ids": invoice_id},
            "$push": {"audit": _audit("link_invoice", user, None, None, {"invoice_id": invoice_id, "match": result["status"]})}})
    await _recompute_po_invoicing(db, ws, co, po_id)
    return {"invoice_id": invoice_id, "po_id": po_id, "matching": result}


async def auto_match(db, ws, co, user, invoice_id, po_reference_text):
    """Deterministic auto-association: unique reliable PO in the ACTIVE company only."""
    inv = await _ap.get_invoice(db, ws, co, invoice_id)
    q = {"workspace_id": ws, "company_id": co, "supplier_id": inv.get("supplier_id"),
         "po_status": {"$in": ["approved", "sent", "partially_invoiced"]}}
    cands = await db.ap_purchase_orders.find(q).to_list(200)
    ref = (po_reference_text or "").strip().lower()
    if ref:
        cands = [c for c in cands if (c.get("number") or "").lower() == ref or ref in (c.get("number") or "").lower()]
    cands = [c for c in cands if (c.get("currency") or "").upper() == (inv.get("currency") or "").upper()]
    if len(cands) != 1:
        return {"matched": False, "reason": "no_unique_candidate", "candidates": len(cands)}
    return {"matched": True, **(await link_invoice(db, ws, co, user, invoice_id, cands[0]["_id"]))}


async def override_match(db, ws, co, user, invoice_id, reason):
    """SENSITIVE. Accepts a tolerance/mismatch exception with reason+audit. NEVER
    bypasses real over-invoicing (that requires PO amendment + re-approval)."""
    inv = await _ap.get_invoice(db, ws, co, invoice_id)
    result = inv.get("matching_result") or {}
    if result.get("exception_kind") == "over_invoicing":
        raise HTTPException(status_code=409, detail="Sur-facturation : override interdit. Amendez et ré-approuvez le PO.")
    if inv.get("matching_status") != "exception":
        raise HTTPException(status_code=409, detail="Aucune exception de matching à déroger.")
    result["overridden"] = True
    result["override_reason"] = reason
    result["override_by"] = user.get("id")
    await db.ap_invoices.update_one({"_id": invoice_id}, {"$set": {
        "matching_status": "overridden", "matching_result": result},
        "$push": {"audit": _ap._audit("match_override", user, "exception", "overridden", {"reason": reason})}})
    return _ap.public_invoice(await _ap.get_invoice(db, ws, co, invoice_id))


async def assert_invoice_matchable(db, ws, co, invoice):
    """Hook called by A4.2 approve: if a PO is linked, matching must be OK/overridden;
    if the supplier requires a PO, a valid linked PO must exist."""
    po_id = invoice.get("purchase_order_id")
    if invoice.get("po_required") and not po_id:
        raise HTTPException(status_code=409, detail="PO obligatoire : liez un bon de commande valide avant approbation.")
    if not po_id:
        return
    # A valid PO object must exist (not a free-text string).
    po = await db.ap_purchase_orders.find_one({"_id": po_id, "workspace_id": ws, "company_id": co})
    if not po:
        raise HTTPException(status_code=409, detail="PO introuvable : approbation bloquée (En attente du PO).")
    ms = invoice.get("matching_status")
    if ms not in ("matched", "within_tolerance", "overridden"):
        raise HTTPException(status_code=409, detail=f"Rapprochement non validé (statut « {ms} ») : résolvez l'exception ou dérogez (permission requise).")


async def ensure_a45_indexes(db):
    await db.ap_purchase_orders.create_index([("workspace_id", 1), ("company_id", 1), ("po_status", 1)])
    await db.ap_purchase_orders.create_index([("workspace_id", 1), ("company_id", 1), ("supplier_id", 1)])
    await db.ap_purchase_orders.create_index([("workspace_id", 1), ("company_id", 1), ("linked_invoice_ids", 1)])
