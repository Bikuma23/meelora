"""A4.1 — Accounts Payable / Achats & Fournisseurs — Supplier repository.

Operational AP layer that REUSES the canonical Financial Core (P2 periods/journal,
A2 workflow, shared tax engine, FX/OANDA, Object Storage). This file (A4.1) covers
ONLY the supplier master data; invoices/payments/PO/matching arrive in A4.2+.

Isolation is workspace_id + company_id on every record (deny-by-default access is
enforced at the API boundary via resolve_effective_access / module level).
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

_SUPPLIER_FIELDS = (
    "code", "name", "trade_name", "legal_address", "remit_to_address",
    "contacts", "primary_contact", "email", "phone", "website",
    "country", "region", "jurisdiction", "language", "default_currency",
    "payment_terms", "due_days", "tax_ids", "tax_regime", "tax_exemptions",
    "bank_info", "preferred_payment_method", "default_expense_account_code",
    "default_ap_account_code", "default_dimensions", "requires_po",
    "internal_notes", "attachments", "status")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mask_bank(bank):
    """Never echo full bank credentials back to the UI — mask the account number."""
    if not isinstance(bank, dict):
        return None
    out = dict(bank)
    for k in ("account", "iban", "account_number"):
        v = out.get(k)
        if isinstance(v, str) and len(v) > 4:
            out[k] = "•" * (len(v) - 4) + v[-4:]
    return out


def public_supplier(d):
    if not d:
        return None
    return {
        "id": d.get("_id"), "code": d.get("code"), "name": d.get("name"),
        "trade_name": d.get("trade_name"), "status": d.get("status", "active"),
        "legal_address": d.get("legal_address"), "remit_to_address": d.get("remit_to_address"),
        "contacts": d.get("contacts") or [], "primary_contact": d.get("primary_contact"),
        "email": d.get("email"), "phone": d.get("phone"), "website": d.get("website"),
        "country": d.get("country"), "region": d.get("region"), "jurisdiction": d.get("jurisdiction"),
        "language": d.get("language"), "default_currency": d.get("default_currency"),
        "payment_terms": d.get("payment_terms"), "due_days": d.get("due_days"),
        "tax_ids": d.get("tax_ids") or {}, "tax_regime": d.get("tax_regime"),
        "tax_exemptions": d.get("tax_exemptions") or [],
        "bank_info": _mask_bank(d.get("bank_info")), "preferred_payment_method": d.get("preferred_payment_method"),
        "default_expense_account_code": d.get("default_expense_account_code"),
        "default_ap_account_code": d.get("default_ap_account_code"),
        "default_dimensions": d.get("default_dimensions") or {},
        "requires_po": bool(d.get("requires_po", False)),
        "internal_notes": d.get("internal_notes"), "attachments": d.get("attachments") or [],
        "credit_balance": d.get("credit_balance", 0.0),
        "created_at": d.get("created_at"), "created_by": d.get("created_by"),
        "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by"),
    }


async def list_suppliers(db, ws, co):
    docs = await db.ap_suppliers.find({"workspace_id": ws, "company_id": co}).sort("name", 1).to_list(2000)
    return [public_supplier(d) for d in docs]


async def get_supplier(db, ws, co, supplier_id):
    d = await db.ap_suppliers.find_one({"_id": supplier_id, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Fournisseur introuvable")
    return d


def _clean(payload):
    changes = {k: payload[k] for k in _SUPPLIER_FIELDS if k in payload}
    if "due_days" in changes and changes["due_days"] in ("", None):
        changes["due_days"] = None
    elif "due_days" in changes:
        try:
            changes["due_days"] = int(changes["due_days"])
        except Exception:
            changes["due_days"] = None
    if changes.get("jurisdiction"):
        changes["jurisdiction"] = str(changes["jurisdiction"]).upper()
    if changes.get("default_currency"):
        changes["default_currency"] = str(changes["default_currency"]).upper()
    if "status" in changes and changes["status"] not in ("active", "inactive"):
        changes["status"] = "active"
    return changes


async def create_supplier(db, ws, co, user, payload):
    if not (payload.get("name") or "").strip():
        raise HTTPException(status_code=422, detail="La raison sociale est requise.")
    doc = {"_id": f"sup_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
           "status": "active", "credit_balance": 0.0, "requires_po": False,
           "created_at": _now(), "created_by": user.get("id")}
    doc.update(_clean(payload))
    await db.ap_suppliers.insert_one(doc)
    return public_supplier(doc)


async def update_supplier(db, ws, co, user, supplier_id, payload):
    await get_supplier(db, ws, co, supplier_id)
    changes = _clean(payload)
    changes["updated_at"] = _now()
    changes["updated_by"] = user.get("id")
    await db.ap_suppliers.update_one({"_id": supplier_id, "workspace_id": ws, "company_id": co}, {"$set": changes})
    return public_supplier(await get_supplier(db, ws, co, supplier_id))


async def ensure_indexes(db):
    await db.ap_suppliers.create_index([("workspace_id", 1), ("company_id", 1), ("name", 1)])
    await db.ap_suppliers.create_index([("workspace_id", 1), ("company_id", 1), ("code", 1)])


# =========================================================================== #
# A4.2 — Supplier invoices (canonical document + 4-status workflow + posting)
# Reuses the shared FX/tax engines and the canonical P2 journal (A2). No 2nd ledger.
# =========================================================================== #
from ..financial import journal as journal_service  # noqa: E402
from ..financial import fx as fx_service  # noqa: E402
from ..financial import tax_engine  # noqa: E402
from ..financial import documents as doc_service  # noqa: E402
from .ar import _resolve_fx, _functional_currency, _next_number, _money  # noqa: E402
from .gl import _get_period, _assert_postable_period  # noqa: E402

_DEFAULT_AP_MAPPING = {
    "ap_account_code": "AP", "default_expense_account_code": "EXPENSE",
    "recoverable_tax_account_code": "TAX_RECOVERABLE", "bank_account_code": "BANK",
    "fx_gain_account_code": "FX_GAIN", "fx_loss_account_code": "FX_LOSS",
}


def _audit(action, user, frm, to, extra=None):
    a = {"action": action, "by": user.get("id"), "by_email": user.get("email"),
         "from": frm, "to": to, "at": _now()}
    if extra:
        a.update(extra)
    return a


async def get_ap_mapping(db, ws, co):
    d = await db.ap_gl_mapping.find_one({"workspace_id": ws, "company_id": co})
    merged = {**_DEFAULT_AP_MAPPING, **{k: v for k, v in (d or {}).items() if k in _DEFAULT_AP_MAPPING and v}}
    return merged


async def set_ap_mapping(db, ws, co, payload):
    changes = {k: v for k, v in payload.items() if k in _DEFAULT_AP_MAPPING and v}
    await db.ap_gl_mapping.update_one({"workspace_id": ws, "company_id": co},
                                      {"$set": {**changes, "updated_at": _now()}}, upsert=True)
    return await get_ap_mapping(db, ws, co)


def public_invoice(d):
    if not d:
        return None
    return {
        "id": d.get("_id"), "supplier_id": d.get("supplier_id"),
        "supplier_invoice_number": d.get("supplier_invoice_number"), "number": d.get("number"),
        "invoice_date": d.get("invoice_date"), "due_date": d.get("due_date"), "due_date_source": d.get("due_date_source"),
        "currency": d.get("currency"), "fx": d.get("fx"),
        "purchase_order_id": d.get("purchase_order_id"), "reference": d.get("reference"), "po_required": bool(d.get("po_required")),
        "lines": d.get("lines") or [], "subtotal": d.get("subtotal"), "tax_total": d.get("tax_total"), "total": d.get("total"),
        "amount_paid": d.get("amount_paid", 0.0), "balance": d.get("balance"),
        "document_status": d.get("document_status", "draft"), "approval_status": d.get("approval_status", "pending"),
        "posting_status": d.get("posting_status", "not_posted"), "payment_status": d.get("payment_status", "unpaid"),
        "source_document_id": d.get("source_document_id"), "source_document_sha256": d.get("source_document_sha256"),
        "journal_entry_id": d.get("journal_entry_id"),
        "period_id": d.get("period_id"), "financial_period_id": d.get("financial_period_id"),
        "financial_year_id": d.get("financial_year_id"),
        "created_by": d.get("created_by"), "created_at": d.get("created_at"),
        "approved_by": d.get("approved_by"), "posted_by": d.get("posted_by"),
        "audit": d.get("audit", []),
    }


async def _compute_ap_lines(db, ws, co, lines, on_date, default_expense):
    if not lines:
        raise HTTPException(status_code=422, detail="Au moins une ligne est requise.")
    tax_cache = {}
    out, subtotal, tax_total = [], 0.0, 0.0
    for ln in lines:
        qty = float(ln.get("qty") if ln.get("qty") is not None else 1)
        unit = float(ln.get("unit_price") or 0)
        net = _money(qty * unit)
        if net < 0:
            raise HTTPException(status_code=422, detail="Montant de ligne négatif interdit.")
        code = ln.get("tax_code") or "EXEMPT"
        if code not in tax_cache:
            tax_cache[code] = await tax_engine.get_tax_code(db, ws, co, code)
        snap = tax_engine.compute_line_tax(tax_cache[code], net, on_date)
        subtotal += net
        tax_total += snap["tax_total"]
        out.append({"description": ln.get("description", ""), "qty": qty, "unit_price": unit,
                    "expense_account_code": ln.get("expense_account_code") or default_expense,
                    "dimensions": ln.get("dimensions") or {}, "tax_code": code,
                    "line_net": net, "tax": snap, "tax_amount": snap["tax_total"]})
    subtotal, tax_total = _money(subtotal), _money(tax_total)
    return out, subtotal, tax_total, _money(subtotal + tax_total)


async def check_duplicate(db, ws, co, supplier_id, number, exclude_id=None):
    """§10 — company + supplier + supplier_invoice_number. Returns the existing
    invoice id when a CERTAIN duplicate exists (never counts rejected ones)."""
    if not (supplier_id and number):
        return None
    q = {"workspace_id": ws, "company_id": co, "supplier_id": supplier_id,
         "supplier_invoice_number": number, "document_status": {"$ne": "rejected"}}
    if exclude_id:
        q["_id"] = {"$ne": exclude_id}
    d = await db.ap_invoices.find_one(q)
    return d["_id"] if d else None


async def list_invoices(db, ws, co, *, document_status=None, supplier_id=None, to_process=False):
    q = {"workspace_id": ws, "company_id": co}
    if document_status:
        q["document_status"] = document_status
    if supplier_id:
        q["supplier_id"] = supplier_id
    if to_process:
        q["document_status"] = {"$in": ["draft", "verified", "submitted", "po_missing", "discrepancy"]}
    docs = await db.ap_invoices.find(q).sort("created_at", -1).to_list(2000)
    return [public_invoice(d) for d in docs]


async def get_invoice(db, ws, co, invoice_id):
    d = await db.ap_invoices.find_one({"_id": invoice_id, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Facture fournisseur introuvable")
    return d


async def create_invoice(db, ws, co, user, payload):
    functional = await _functional_currency(db, ws, co)
    supplier = await get_supplier(db, ws, co, payload["supplier_id"])
    period = await _get_period(db, ws, co, payload["period_id"])
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : création impossible.")
    currency = (payload.get("currency") or supplier.get("default_currency") or functional).upper()
    invoice_date = payload.get("invoice_date") or _now()[:10]
    # §3 — due date snapshot from the supplier payment terms; manual override allowed/audited.
    due_date = payload.get("due_date")
    due_source = "manual" if due_date else None
    if not due_date:
        dd = supplier.get("due_days")
        if dd is None:
            import re
            m = re.search(r"(\d+)", str(supplier.get("payment_terms") or ""))
            dd = int(m.group(1)) if m else None
        if dd is not None:
            from datetime import date as _date, timedelta as _td
            try:
                due_date = (_date.fromisoformat(invoice_date) + _td(days=int(dd))).isoformat()
                due_source = "supplier_terms"
            except Exception:
                due_date = None
    mapping = await get_ap_mapping(db, ws, co)
    default_exp = supplier.get("default_expense_account_code") or mapping["default_expense_account_code"]
    lines, subtotal, tax_total, total = await _compute_ap_lines(
        db, ws, co, payload.get("lines"), invoice_date, default_exp)
    fx = await _resolve_fx(db, ws, co, currency, functional, invoice_date, payload.get("fx_rate"))
    doc = {"_id": f"sinv_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
           "supplier_id": supplier["_id"], "supplier_invoice_number": (payload.get("supplier_invoice_number") or "").strip() or None,
           "invoice_date": invoice_date, "due_date": due_date, "due_date_source": due_source,
           "currency": currency, "fx": fx,
           "purchase_order_id": payload.get("purchase_order_id"), "reference": payload.get("reference"),
           "po_required": bool(supplier.get("requires_po", False)),
           "period_id": period["_id"], "financial_period_id": period["_id"], "financial_year_id": period.get("financial_year_id"),
           "lines": lines, "subtotal": subtotal, "tax_total": tax_total, "total": total,
           "amount_paid": 0.0, "balance": total,
           "document_status": "draft", "approval_status": "pending", "posting_status": "not_posted", "payment_status": "unpaid",
           "created_by": user.get("id"), "created_at": _now(), "audit": [_audit("create", user, None, "draft")]}
    await db.ap_invoices.insert_one(doc)
    return public_invoice(doc)


async def _require_doc_status(db, ws, co, invoice_id, expected):
    d = await get_invoice(db, ws, co, invoice_id)
    if d.get("document_status") not in (expected if isinstance(expected, (list, tuple)) else [expected]):
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('document_status')} ».")
    return d


async def update_draft(db, ws, co, user, invoice_id, payload):
    d = await _require_doc_status(db, ws, co, invoice_id, "draft")
    functional = await _functional_currency(db, ws, co)
    changes = {}
    currency = (payload.get("currency") or d["currency"]).upper()
    invoice_date = payload.get("invoice_date") or d["invoice_date"]
    if payload.get("lines") is not None:
        supplier = await get_supplier(db, ws, co, d["supplier_id"])
        mapping = await get_ap_mapping(db, ws, co)
        default_exp = supplier.get("default_expense_account_code") or mapping["default_expense_account_code"]
        lines, subtotal, tax_total, total = await _compute_ap_lines(db, ws, co, payload["lines"], invoice_date, default_exp)
        changes.update({"lines": lines, "subtotal": subtotal, "tax_total": tax_total, "total": total, "balance": total})
    for f in ("supplier_invoice_number", "purchase_order_id", "reference"):
        if payload.get(f) is not None:
            changes[f] = payload[f]
    if payload.get("due_date") is not None:
        changes["due_date"] = payload["due_date"]
        changes["due_date_source"] = "manual"
    if payload.get("currency") or payload.get("invoice_date") or payload.get("fx_rate") is not None:
        changes["currency"] = currency
        changes["invoice_date"] = invoice_date
        changes["fx"] = await _resolve_fx(db, ws, co, currency, functional, invoice_date, payload.get("fx_rate"))
    if changes:
        await db.ap_invoices.update_one({"_id": invoice_id}, {"$set": changes, "$push": {"audit": _audit("update", user, "draft", "draft")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def _assert_po_ok(d):
    """§9 — PO required but none present → block and mark po_missing."""
    if d.get("po_required") and not d.get("purchase_order_id"):
        return False
    return True


async def verify_invoice(db, ws, co, user, invoice_id):
    d = await _require_doc_status(db, ws, co, invoice_id, "draft")
    if not d.get("lines"):
        raise HTTPException(status_code=422, detail="Facture vide.")
    await db.ap_invoices.update_one({"_id": invoice_id}, {
        "$set": {"document_status": "verified", "verified_by": user.get("id")},
        "$push": {"audit": _audit("verify", user, "draft", "verified")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def submit_invoice(db, ws, co, user, invoice_id):
    d = await _require_doc_status(db, ws, co, invoice_id, ["verified", "po_missing"])
    dup = await check_duplicate(db, ws, co, d.get("supplier_id"), d.get("supplier_invoice_number"), exclude_id=invoice_id)
    if dup:
        raise HTTPException(status_code=409, detail=f"Doublon certain : une facture avec ce numéro existe déjà pour ce fournisseur ({dup}).")
    if not await _assert_po_ok(d):
        await db.ap_invoices.update_one({"_id": invoice_id}, {
            "$set": {"document_status": "po_missing"},
            "$push": {"audit": _audit("po_missing", user, d.get("document_status"), "po_missing")}})
        raise HTTPException(status_code=409, detail="PO obligatoire manquant : la facture reste dans « Factures à traiter ».")
    await db.ap_invoices.update_one({"_id": invoice_id}, {
        "$set": {"document_status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _audit("submit", user, d.get("document_status"), "submitted")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def approve_invoice(db, ws, co, user, invoice_id):
    d = await _require_doc_status(db, ws, co, invoice_id, "submitted")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403, detail="Séparation des tâches : le créateur ne peut pas approuver sa facture.")
    if not await _assert_po_ok(d):
        raise HTTPException(status_code=409, detail="PO obligatoire manquant : approbation bloquée.")
    dup = await check_duplicate(db, ws, co, d.get("supplier_id"), d.get("supplier_invoice_number"), exclude_id=invoice_id)
    if dup:
        raise HTTPException(status_code=409, detail=f"Doublon certain : approbation bloquée ({dup}).")
    # Freeze the source PDF version if one was uploaded (§11/§14). No PDF is generated
    # for a supplier document (the original is authoritative).
    sset = {"document_status": "approved", "approval_status": "approved", "approved_by": user.get("id"), "approved_at": _now()}
    if d.get("source_document_id"):
        await db.documents.update_one({"_id": d["source_document_id"], "workspace_id": ws, "company_id": co},
                                      {"$set": {"frozen": True}})
    await db.ap_invoices.update_one({"_id": invoice_id}, {
        "$set": sset, "$push": {"audit": _audit("approve", user, "submitted", "approved")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def reject_invoice(db, ws, co, user, invoice_id, reason=None):
    d = await _require_doc_status(db, ws, co, invoice_id, ["verified", "submitted", "po_missing", "discrepancy"])
    await db.ap_invoices.update_one({"_id": invoice_id}, {
        "$set": {"document_status": "rejected", "approval_status": "rejected", "rejected_by": user.get("id"), "reject_reason": reason},
        "$push": {"audit": _audit("reject", user, d.get("document_status"), "rejected", {"reason": reason})}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def post_invoice(db, ws, co, user, invoice_id):
    d = await get_invoice(db, ws, co, invoice_id)
    if d.get("posting_status") == "posted" and d.get("journal_entry_id"):
        return public_invoice(d)  # idempotent
    if d.get("document_status") != "approved":
        raise HTTPException(status_code=409, detail=f"Seule une facture approuvée peut être comptabilisée (statut « {d.get('document_status')} »).")
    period = await _get_period(db, ws, co, d["period_id"])
    await _assert_postable_period(db, ws, co, period)
    mapping = await get_ap_mapping(db, ws, co)
    rate = d["fx"]["rate"]
    gl_lines, debits_func = [], 0.0
    for ln in d["lines"]:
        net_func = fx_service.convert(ln["line_net"], rate)
        if net_func:
            gl_lines.append({"account": ln["expense_account_code"], "description": ln.get("description") or "Charge",
                             "debit": net_func, "credit": 0, "txn_debit": ln["line_net"], "txn_currency": d["currency"]})
            debits_func += net_func
    tax_func = fx_service.convert(d.get("tax_total") or 0, rate)
    if tax_func:
        gl_lines.append({"account": mapping["recoverable_tax_account_code"], "description": "Taxes récupérables (CTI)",
                         "debit": tax_func, "credit": 0, "txn_debit": d.get("tax_total"), "txn_currency": d["currency"]})
        debits_func += tax_func
    ap_func = _money(debits_func)
    gl_lines.append({"account": mapping["ap_account_code"], "description": "Comptes fournisseurs",
                     "debit": 0, "credit": ap_func, "txn_credit": d["total"], "txn_currency": d["currency"]})
    ref = d.get("supplier_invoice_number") or d["_id"]
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=d["invoice_date"], reference=ref, description=f"Facture fournisseur {ref}",
        lines=gl_lines, external_id=invoice_id, source_type="supplier_invoice", source_system="purchases",
        transaction_currency=d["currency"], fx=d["fx"])
    if d.get("source_document_id"):
        await doc_service.link_journal(db, ws, co, d["source_document_id"], je["_id"])
    await db.ap_invoices.update_one({"_id": invoice_id}, {
        "$set": {"posting_status": "posted", "posted_by": user.get("id"), "posted_at": _now(), "journal_entry_id": je["_id"]},
        "$push": {"audit": _audit("post", user, "approved", "posted")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


# =========================================================================== #
# A4.3 — Supplier PAYMENTS · CREDIT NOTES · AGING · PAYMENT BATCHES
#
# Cardinal rules (validated with the product owner):
#  - A payment has a 5-state lifecycle: draft → prepared → authorized →
#    executed → posted (+ cancelled). Only EXECUTED (+ its allocations) affects
#    invoice.payment_status; only POSTED creates a canonical P2 journal.
#  - preparing ≠ authorizing ≠ executing ≠ posting ≠ reconciling. The future
#    Bank & Treasury engine will CONSUME this same ap_payment (no 2nd object).
#  - Allocations are a traceable registry (active flag + history), never a
#    single overwritable amount. Applying an advance later never re-disburses
#    cash nor re-posts a bank movement.
#  - A payment executed before its invoice is posted keeps the economic event;
#    posting the invoice + posting the payment yields the SAME final GL result
#    as invoice-then-pay, with no double entry (independent, idempotent journals).
# =========================================================================== #
from ..financial import fx as _fx  # noqa: E402  (alias, fx_service already imported)

_PAYMENT_STATES = ("draft", "prepared", "authorized", "executed", "posted", "cancelled")
# invoice.payment_status is DERIVED from executed allocations + posted credits only.
_PAY_STATUS = ("unpaid", "partially_paid", "paid")


def _pay_audit(action, user, frm, to, extra=None):
    a = {"action": action, "by": user.get("id"), "by_email": user.get("email"),
         "from": frm, "to": to, "at": _now()}
    if extra:
        a.update(extra)
    return a


def public_payment(d):
    if not d:
        return None
    allocs = [{"id": a.get("id"), "invoice_id": a.get("invoice_id"),
               "amount_applied": a.get("amount_applied"), "currency": a.get("currency"),
               "invoice_fx_rate": a.get("invoice_fx_rate"), "active": a.get("active", True),
               "allocated_at": a.get("allocated_at"), "allocated_by": a.get("allocated_by"),
               "deallocated_at": a.get("deallocated_at")} for a in (d.get("allocations") or [])]
    applied = _money(sum(float(a["amount_applied"] or 0) for a in allocs if a.get("active", True)))
    return {
        "id": d.get("_id"), "supplier_id": d.get("supplier_id"), "payment_state": d.get("payment_state", "draft"),
        "amount": d.get("amount"), "currency": d.get("currency"), "fx": d.get("fx"),
        "payment_date": d.get("payment_date"), "value_date": d.get("value_date"),
        "method": d.get("method"), "bank_account": d.get("bank_account"), "bank_reference": d.get("bank_reference"),
        "note": d.get("note"), "allocations": allocs, "applied_amount": applied,
        "unapplied_amount": _money(float(d.get("amount") or 0) - applied),
        "realized_fx": d.get("realized_fx", 0.0), "journal_entry_id": d.get("journal_entry_id"),
        "posting_status": ("posted" if d.get("journal_entry_id") else "not_posted"),
        "period_id": d.get("period_id"), "batch_id": d.get("batch_id"),
        "external_ref": d.get("external_ref"), "idempotency_key": d.get("idempotency_key"),
        "execution_method": d.get("execution_method"), "execution_reference": d.get("execution_reference"),
        "executed_at": d.get("executed_at"), "executed_by": d.get("executed_by"),
        "attachments": d.get("attachments") or [],
        "created_by": d.get("created_by"), "created_at": d.get("created_at"), "audit": d.get("audit", []),
    }


async def get_payment(db, ws, co, pid):
    d = await db.ap_payments.find_one({"_id": pid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Paiement fournisseur introuvable")
    return d


async def list_payments(db, ws, co, *, supplier_id=None, invoice_id=None, payment_state=None):
    q = {"workspace_id": ws, "company_id": co}
    if supplier_id:
        q["supplier_id"] = supplier_id
    if payment_state:
        q["payment_state"] = payment_state
    if invoice_id:
        q["allocations.invoice_id"] = invoice_id
    docs = await db.ap_payments.find(q).sort("created_at", -1).to_list(2000)
    return [public_payment(d) for d in docs]


async def _invoice_open_balance(inv):
    """Balance still OWED = total − posted credits − executed payment allocations."""
    return _money(float(inv.get("total") or 0) - float(inv.get("credited_total") or 0) - float(inv.get("amount_paid") or 0))


async def _recompute_invoice_payment(db, ws, co, invoice_id):
    """invoice.payment_status is derived ONLY from EXECUTED/POSTED payment
    allocations (never from draft/prepared/authorized) + POSTED credit notes.
    The payment/credit documents remain the source of truth (invoice history is
    never rewritten destructively — only the derived cache is refreshed)."""
    inv = await db.ap_invoices.find_one({"_id": invoice_id, "workspace_id": ws, "company_id": co})
    if not inv:
        return
    paid = 0.0
    async for p in db.ap_payments.find({"workspace_id": ws, "company_id": co,
                                        "payment_state": {"$in": ["executed", "posted"]},
                                        "allocations.invoice_id": invoice_id}):
        for a in p.get("allocations") or []:
            if a.get("invoice_id") == invoice_id and a.get("active", True):
                paid += float(a.get("amount_applied") or 0)
    credited = 0.0
    async for cn in db.ap_credit_notes.find({"workspace_id": ws, "company_id": co,
                                             "status": "posted", "invoice_id": invoice_id}):
        credited += float(cn.get("total") or 0)
    paid, credited = _money(paid), _money(credited)
    total = float(inv.get("total") or 0)
    balance = _money(total - credited - paid)
    if paid <= 0.001 and credited <= 0.001:
        status = "unpaid"
    elif balance <= 0.001:
        status = "paid"
    else:
        status = "partially_paid"
    await db.ap_invoices.update_one({"_id": invoice_id}, {"$set": {
        "amount_paid": paid, "credited_total": credited, "balance": max(balance, 0.0), "payment_status": status}})


async def _validate_allocations(db, ws, co, supplier_id, currency, requested, *, exclude_payment_id=None):
    """Normalize allocation lines; enforce same-currency + same-supplier + not
    over-allocating the invoice open balance (considering OTHER executed/posted
    payments so two concurrent payments cannot over-pay the same portion)."""
    out, total = [], 0.0
    for rl in requested or []:
        inv = await get_invoice(db, ws, co, rl["invoice_id"])
        if inv.get("supplier_id") != supplier_id:
            raise HTTPException(status_code=422, detail="Une facture allouée n'appartient pas au fournisseur du paiement.")
        if inv.get("document_status") not in ("approved",):
            raise HTTPException(status_code=409, detail="Seule une facture approuvée peut être réglée.")
        if (inv.get("currency") or "").upper() != currency:
            raise HTTPException(status_code=422, detail="A4.3 : allocation dans la devise de la facture uniquement (pas de conversion croisée).")
        amount = _money(rl.get("amount"))
        if amount <= 0:
            raise HTTPException(status_code=422, detail="Montant d'allocation invalide.")
        open_bal = await _invoice_open_balance(inv)
        if amount > open_bal + 0.001:
            raise HTTPException(status_code=422, detail=f"Sur-affectation : allocation ({amount}) > solde dû ({open_bal}) de la facture {inv.get('supplier_invoice_number') or inv['_id']}.")
        out.append({"id": f"alloc_{uuid.uuid4().hex}", "invoice_id": inv["_id"], "amount_applied": amount,
                    "currency": currency, "invoice_fx_rate": (inv.get("fx") or {}).get("rate", 1.0),
                    "active": True, "allocated_at": _now(), "allocated_by": None})
        total += amount
    return out, _money(total)


async def create_payment(db, ws, co, user, payload):
    """Create a DRAFT payment (no cash out, no GL, no invoice mutation)."""
    supplier = await get_supplier(db, ws, co, payload["supplier_id"])
    functional = await _functional_currency(db, ws, co)
    currency = (payload.get("currency") or supplier.get("default_currency") or functional).upper()
    amount = _money(payload.get("amount"))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Montant de paiement invalide.")
    pay_date = payload.get("payment_date") or _now()[:10]
    allocs, alloc_total = await _validate_allocations(db, ws, co, supplier["_id"], currency, payload.get("allocations"))
    if alloc_total > amount + 0.001:
        raise HTTPException(status_code=422, detail=f"Les allocations ({alloc_total}) dépassent le montant du paiement ({amount}).")
    for a in allocs:
        a["allocated_by"] = user.get("id")
    fx = await _resolve_fx(db, ws, co, currency, functional, pay_date, payload.get("fx_rate"))
    doc = {"_id": f"pay_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co, "supplier_id": supplier["_id"],
           "payment_state": "draft", "amount": amount, "currency": currency, "fx": fx,
           "payment_date": pay_date, "value_date": payload.get("value_date") or pay_date,
           "method": payload.get("method") or "bank_transfer", "bank_account": payload.get("bank_account"),
           "bank_reference": payload.get("bank_reference"), "note": payload.get("note"),
           "allocations": allocs, "realized_fx": 0.0, "journal_entry_id": None,
           "period_id": payload.get("period_id"), "batch_id": payload.get("batch_id"),
           "idempotency_key": f"appay_{uuid.uuid4().hex}", "external_ref": None, "attachments": [],
           "created_by": user.get("id"), "created_at": _now(),
           "audit": [_pay_audit("create", user, None, "draft")]}
    await db.ap_payments.insert_one(doc)
    return public_payment(doc)


async def update_payment(db, ws, co, user, pid, payload):
    d = await get_payment(db, ws, co, pid)
    if d.get("payment_state") not in ("draft", "prepared"):
        raise HTTPException(status_code=409, detail="Un paiement autorisé/exécuté ne peut plus être modifié (créez une réaffectation tracée).")
    functional = await _functional_currency(db, ws, co)
    changes = {}
    currency = (payload.get("currency") or d["currency"]).upper()
    pay_date = payload.get("payment_date") or d["payment_date"]
    if payload.get("amount") is not None:
        changes["amount"] = _money(payload["amount"])
    for f in ("value_date", "method", "bank_account", "bank_reference", "note"):
        if payload.get(f) is not None:
            changes[f] = payload[f]
    if payload.get("allocations") is not None:
        allocs, alloc_total = await _validate_allocations(db, ws, co, d["supplier_id"], currency, payload["allocations"])
        for a in allocs:
            a["allocated_by"] = user.get("id")
        amt = changes.get("amount", d["amount"])
        if alloc_total > amt + 0.001:
            raise HTTPException(status_code=422, detail=f"Les allocations ({alloc_total}) dépassent le montant ({amt}).")
        changes["allocations"] = allocs
    if payload.get("currency") or payload.get("payment_date") or payload.get("fx_rate") is not None:
        changes["currency"], changes["payment_date"] = currency, pay_date
        changes["fx"] = await _resolve_fx(db, ws, co, currency, functional, pay_date, payload.get("fx_rate"))
    if changes:
        await db.ap_payments.update_one({"_id": pid}, {"$set": changes, "$push": {"audit": _pay_audit("update", user, d["payment_state"], d["payment_state"])}})
    return public_payment(await get_payment(db, ws, co, pid))


async def _transition_payment(db, ws, co, user, pid, allowed_from, to, action):
    d = await get_payment(db, ws, co, pid)
    if d.get("payment_state") not in allowed_from:
        raise HTTPException(status_code=409, detail=f"Transition impossible : état « {d.get('payment_state')} ».")
    await db.ap_payments.update_one({"_id": pid}, {
        "$set": {"payment_state": to},
        "$push": {"audit": _pay_audit(action, user, d.get("payment_state"), to)}})
    return await get_payment(db, ws, co, pid)


async def prepare_payment(db, ws, co, user, pid):
    return public_payment(await _transition_payment(db, ws, co, user, pid, ("draft",), "prepared", "prepare"))


async def authorize_payment(db, ws, co, user, pid):
    return public_payment(await _transition_payment(db, ws, co, user, pid, ("prepared",), "authorized", "authorize"))


async def cancel_payment(db, ws, co, user, pid):
    d = await get_payment(db, ws, co, pid)
    if d.get("payment_state") in ("executed", "posted"):
        raise HTTPException(status_code=409, detail="Un paiement exécuté/comptabilisé ne peut être annulé (utilisez une extourne/remboursement).")
    return public_payment(await _transition_payment(db, ws, co, user, pid, ("draft", "prepared", "authorized"), "cancelled", "cancel"))


async def mark_executed(db, ws, co, user, pid, payload):
    """authorized → executed. Controlled 'the disbursement really happened'
    action (actor/timestamp/method/reference/audit). SENSITIVE. This is what
    makes the payment count toward invoice.payment_status — NOT the GL posting.
    A future Bank & Treasury module will replace/confirm this without creating a
    second financial object."""
    d = await get_payment(db, ws, co, pid)
    if d.get("payment_state") != "authorized":
        raise HTTPException(status_code=409, detail=f"Seul un paiement autorisé peut être marqué exécuté (état « {d.get('payment_state')} »).")
    exec_ref = (payload or {}).get("execution_reference")
    exec_method = (payload or {}).get("execution_method") or d.get("method")
    await db.ap_payments.update_one({"_id": pid}, {"$set": {
        "payment_state": "executed", "executed_at": _now(), "executed_by": user.get("id"),
        "execution_method": exec_method, "execution_reference": exec_ref,
        "external_ref": (payload or {}).get("external_ref") or d.get("external_ref")},
        "$push": {"audit": _pay_audit("execute", user, "authorized", "executed",
                                      {"method": exec_method, "reference": exec_ref})}})
    for a in d.get("allocations") or []:
        if a.get("active", True):
            await _recompute_invoice_payment(db, ws, co, a["invoice_id"])
    return public_payment(await get_payment(db, ws, co, pid))


async def post_payment(db, ws, co, user, pid):
    """executed → posted. Canonical P2 journal: Dr Fournisseurs / Cr Banque
    (+ realised FX). Balanced, atomic, idempotent. Locked/closed periods block
    ONLY the accounting posting — the executed economic event is preserved."""
    d = await get_payment(db, ws, co, pid)
    if d.get("journal_entry_id"):
        return public_payment(d)  # idempotent
    if d.get("payment_state") != "executed":
        raise HTTPException(status_code=409, detail="Seul un paiement exécuté peut être comptabilisé.")
    period_id = d.get("period_id")
    if not period_id:
        allocs = d.get("allocations") or []
        if allocs:
            first_inv = await get_invoice(db, ws, co, allocs[0]["invoice_id"])
            period_id = first_inv["period_id"]
    if not period_id:
        raise HTTPException(status_code=422, detail="Période comptable requise pour comptabiliser le paiement.")
    period = await _get_period(db, ws, co, period_id)
    await _assert_postable_period(db, ws, co, period)
    mapping = await get_ap_mapping(db, ws, co)
    pay_rate = d["fx"]["rate"]
    gl, debits_func = [], 0.0
    applied_total = 0.0
    for a in d.get("allocations") or []:
        if not a.get("active", True):
            continue
        ap_func = _fx.convert(a["amount_applied"], a.get("invoice_fx_rate") or pay_rate)  # AP relieved at INVOICE rate
        if ap_func:
            gl.append({"account": mapping["ap_account_code"], "description": "Règlement facture fournisseur",
                       "debit": ap_func, "credit": 0, "txn_debit": a["amount_applied"], "txn_currency": d["currency"]})
            debits_func += ap_func
        applied_total += a["amount_applied"]
    advance = _money(float(d["amount"]) - applied_total)
    if advance > 0.001:  # unapplied advance sits in AP as a supplier prepayment (at payment rate)
        adv_func = _fx.convert(advance, pay_rate)
        gl.append({"account": mapping["ap_account_code"], "description": "Avance / paiement non affecté fournisseur",
                   "debit": adv_func, "credit": 0, "txn_debit": advance, "txn_currency": d["currency"]})
        debits_func += adv_func
    bank_func = _fx.convert(d["amount"], pay_rate)
    gl.append({"account": mapping["bank_account_code"], "description": "Décaissement bancaire",
               "debit": 0, "credit": bank_func, "txn_credit": d["amount"], "txn_currency": d["currency"]})
    diff = round(_money(debits_func) - bank_func, 2)  # realised FX to balance (functional)
    realized = 0.0
    if diff < -0.001:      # debits < credits → extra debit = FX loss
        gl.append({"account": mapping["fx_loss_account_code"], "description": "Perte de change réalisée", "debit": -diff, "credit": 0})
        realized = diff
    elif diff > 0.001:     # debits > credits → extra credit = FX gain
        gl.append({"account": mapping["fx_gain_account_code"], "description": "Gain de change réalisé", "debit": 0, "credit": diff})
        realized = diff
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=period.get("financial_year_id"), financial_period_id=period["_id"],
        entry_date=d.get("value_date") or d["payment_date"], reference=f"PAY-{d['_id'][-8:]}",
        description="Paiement fournisseur", lines=gl, external_id=d["_id"],
        source_type="supplier_payment", source_system="purchases", transaction_currency=d["currency"], fx=d["fx"])
    await db.ap_payments.update_one({"_id": pid}, {"$set": {
        "payment_state": "posted", "journal_entry_id": je["_id"], "realized_fx": realized,
        "posted_by": user.get("id"), "posted_at": _now()},
        "$push": {"audit": _pay_audit("post", user, "executed", "posted")}})
    return public_payment(await get_payment(db, ws, co, pid))


async def allocate_advance(db, ws, co, user, pid, payload):
    """Apply an executed/posted payment's UNAPPLIED amount to an invoice. A
    distinct traceable event — never re-disburses cash nor re-posts a bank
    movement (the advance already sits in AP)."""
    d = await get_payment(db, ws, co, pid)
    if d.get("payment_state") not in ("executed", "posted"):
        raise HTTPException(status_code=409, detail="Seul un paiement exécuté peut être affecté.")
    applied = _money(sum(float(a["amount_applied"] or 0) for a in d.get("allocations") or [] if a.get("active", True)))
    unapplied = _money(float(d["amount"]) - applied)
    inv = await get_invoice(db, ws, co, payload["invoice_id"])
    if inv.get("supplier_id") != d["supplier_id"]:
        raise HTTPException(status_code=422, detail="La facture n'appartient pas au fournisseur du paiement.")
    if (inv.get("currency") or "").upper() != d["currency"]:
        raise HTTPException(status_code=422, detail="Affectation dans la devise du paiement uniquement.")
    amount = _money(payload.get("amount"))
    if amount <= 0 or amount > unapplied + 0.001:
        raise HTTPException(status_code=422, detail=f"Montant à affecter invalide (disponible : {unapplied}).")
    open_bal = await _invoice_open_balance(inv)
    if amount > open_bal + 0.001:
        raise HTTPException(status_code=422, detail=f"Sur-affectation : {amount} > solde dû {open_bal}.")
    alloc = {"id": f"alloc_{uuid.uuid4().hex}", "invoice_id": inv["_id"], "amount_applied": amount,
             "currency": d["currency"], "invoice_fx_rate": (inv.get("fx") or {}).get("rate", 1.0),
             "active": True, "allocated_at": _now(), "allocated_by": user.get("id")}
    await db.ap_payments.update_one({"_id": pid}, {"$push": {"allocations": alloc,
        "audit": _pay_audit("allocate", user, d["payment_state"], d["payment_state"], {"invoice_id": inv["_id"], "amount": amount})}})
    await _recompute_invoice_payment(db, ws, co, inv["_id"])
    return public_payment(await get_payment(db, ws, co, pid))


# --------------------------------------------------------------------------- #
# Supplier credit notes — own workflow + own canonical journal (reversal-style)
# --------------------------------------------------------------------------- #
def public_credit_note(d):
    if not d:
        return None
    return {"id": d.get("_id"), "supplier_id": d.get("supplier_id"), "invoice_id": d.get("invoice_id"),
            "number": d.get("number"), "status": d.get("status", "draft"), "currency": d.get("currency"), "fx": d.get("fx"),
            "lines": d.get("lines") or [], "subtotal": d.get("subtotal"), "tax_total": d.get("tax_total"), "total": d.get("total"),
            "period_id": d.get("period_id"), "financial_year_id": d.get("financial_year_id"),
            "journal_entry_id": d.get("journal_entry_id"), "creates_supplier_credit": d.get("creates_supplier_credit", False),
            "created_by": d.get("created_by"), "approved_by": d.get("approved_by"), "posted_by": d.get("posted_by"),
            "created_at": d.get("created_at"), "audit": d.get("audit", [])}


async def get_credit_note(db, ws, co, cid):
    d = await db.ap_credit_notes.find_one({"_id": cid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Note de crédit fournisseur introuvable")
    return d


async def list_credit_notes(db, ws, co, *, invoice_id=None, supplier_id=None, status=None):
    q = {"workspace_id": ws, "company_id": co}
    if invoice_id:
        q["invoice_id"] = invoice_id
    if supplier_id:
        q["supplier_id"] = supplier_id
    if status:
        q["status"] = status
    docs = await db.ap_credit_notes.find(q).sort("created_at", -1).to_list(2000)
    return [public_credit_note(d) for d in docs]


async def create_credit_note(db, ws, co, user, payload):
    """Autonomous AP credit against a POSTED supplier invoice. Reuses the
    ORIGINAL invoice tax + FX snapshot (never recomputes with current rates).
    Cumulative over-credit guard: billed − posted credits − pending credits −
    new ≥ 0 per line."""
    inv = await get_invoice(db, ws, co, payload["invoice_id"])
    if inv.get("posting_status") != "posted":
        raise HTTPException(status_code=409, detail="Note de crédit possible seulement sur une facture comptabilisée.")
    req_lines = payload.get("lines") or []
    if not req_lines:
        raise HTTPException(status_code=422, detail="Au moins une ligne à créditer est requise.")
    period = await _get_period(db, ws, co, payload.get("period_id") or inv["period_id"])
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée.")
    # Pending (submitted/approved but not posted) credited amounts per line, to
    # stop two users preparing a simultaneous over-credit.
    pending = {}
    async for cn in db.ap_credit_notes.find({"workspace_id": ws, "company_id": co,
                                             "invoice_id": inv["_id"], "status": {"$in": ["submitted", "approved"]}}):
        for ln in cn.get("lines") or []:
            pending[ln["invoice_line_index"]] = pending.get(ln["invoice_line_index"], 0.0) + float(ln.get("net_credit") or 0)
    out_lines, subtotal, tax_total = [], 0.0, 0.0
    for rl in req_lines:
        idx = int(rl.get("invoice_line_index"))
        if idx < 0 or idx >= len(inv["lines"]):
            raise HTTPException(status_code=422, detail="Ligne de facture invalide.")
        src = inv["lines"][idx]
        credit_net = _money(rl.get("net_credit"))
        posted_credited = float(src.get("credited_net", 0.0))
        remaining = _money(src["line_net"] - posted_credited - pending.get(idx, 0.0))
        if credit_net <= 0:
            raise HTTPException(status_code=422, detail="Montant à créditer invalide.")
        if credit_net > remaining + 0.001:
            raise HTTPException(status_code=422, detail=f"Sur-crédit interdit (ligne {idx}) : restant créditable {remaining} (crédits comptabilisés + en attente déduits).")
        ratio = (credit_net / src["line_net"]) if src["line_net"] else 0
        comps = [{"name": c["name"], "tax_type": c["tax_type"], "rate": c["rate"],
                  "payable_account_code": c.get("payable_account_code") or c.get("account_code"),
                  "amount": _money(c["amount"] * ratio)} for c in (src.get("tax") or {}).get("components", [])]
        line_tax = _money(sum(c["amount"] for c in comps))
        subtotal += credit_net
        tax_total += line_tax
        out_lines.append({"invoice_line_index": idx, "description": src.get("description", ""),
                          "expense_account_code": src.get("expense_account_code"),
                          "dimensions": src.get("dimensions") or {}, "net_credit": credit_net,
                          "tax": {"components": comps, "tax_total": line_tax}})
    subtotal, tax_total = _money(subtotal), _money(tax_total)
    doc = {"_id": f"scn_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co, "number": None,
           "supplier_id": inv["supplier_id"], "invoice_id": inv["_id"], "status": "draft",
           "currency": inv["currency"], "fx": inv["fx"], "lines": out_lines,
           "subtotal": subtotal, "tax_total": tax_total, "total": _money(subtotal + tax_total),
           "period_id": period["_id"], "financial_period_id": period["_id"], "financial_year_id": period.get("financial_year_id"),
           "created_by": user.get("id"), "created_at": _now(), "audit": [_pay_audit("create", user, None, "draft")]}
    await db.ap_credit_notes.insert_one(doc)
    return public_credit_note(doc)


async def _require_cn_status(db, ws, co, cid, expected):
    d = await get_credit_note(db, ws, co, cid)
    if d.get("status") != expected:
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    return d


async def submit_credit_note(db, ws, co, user, cid):
    await _require_cn_status(db, ws, co, cid, "draft")
    await db.ap_credit_notes.update_one({"_id": cid}, {"$set": {"status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _pay_audit("submit", user, "draft", "submitted")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


async def approve_credit_note(db, ws, co, user, cid):
    d = await _require_cn_status(db, ws, co, cid, "submitted")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403, detail="Séparation des tâches : le créateur ne peut pas approuver la note de crédit.")
    await db.ap_credit_notes.update_one({"_id": cid}, {"$set": {"status": "approved", "approved_by": user.get("id")},
        "$push": {"audit": _pay_audit("approve", user, "submitted", "approved")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


async def post_credit_note(db, ws, co, user, cid):
    """approved → posted. Canonical journal reversing the ORIGINAL charge lines
    proportionally: Dr Fournisseurs / Cr Charge(s) / Cr Taxes récupérables (at
    the ORIGINAL invoice rate). Immutable once posted."""
    d = await get_credit_note(db, ws, co, cid)
    if d.get("journal_entry_id"):
        return public_credit_note(d)  # idempotent
    if d.get("status") != "approved":
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    period = await _get_period(db, ws, co, d["period_id"])
    await _assert_postable_period(db, ws, co, period)
    inv = await get_invoice(db, ws, co, d["invoice_id"])
    mapping = await get_ap_mapping(db, ws, co)
    rate = d["fx"]["rate"]
    gl, credits_func = [], 0.0
    for ln in d["lines"]:
        net_func = _fx.convert(ln["net_credit"], rate)
        if net_func:
            gl.append({"account": ln.get("expense_account_code") or mapping["default_expense_account_code"],
                       "description": "Crédit charge fournisseur", "debit": 0, "credit": net_func,
                       "txn_credit": ln["net_credit"], "txn_currency": d["currency"]})
            credits_func += net_func
        for c in ln["tax"]["components"]:
            amt_func = _fx.convert(c["amount"], rate)
            if amt_func:
                gl.append({"account": c.get("payable_account_code") or mapping["recoverable_tax_account_code"],
                           "description": f"Crédit {c['name']}", "debit": 0, "credit": amt_func,
                           "txn_credit": c["amount"], "txn_currency": d["currency"]})
                credits_func += amt_func
    ap_func = _money(credits_func)
    gl.insert(0, {"account": mapping["ap_account_code"], "description": "Réduction comptes fournisseurs",
                  "debit": ap_func, "credit": 0, "txn_debit": d["total"], "txn_currency": d["currency"]})
    number = await _next_number(db, ws, co, "SCN", _now()[:4])
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=_now()[:10], reference=number, description=f"Note de crédit fournisseur {number} (facture {inv.get('supplier_invoice_number')})",
        lines=gl, external_id=cid, source_type="supplier_credit_note", source_system="purchases",
        transaction_currency=d["currency"], fx=d["fx"])
    for ln in d["lines"]:
        inv["lines"][ln["invoice_line_index"]]["credited_net"] = _money(
            inv["lines"][ln["invoice_line_index"]].get("credited_net", 0.0) + ln["net_credit"])
    await db.ap_invoices.update_one({"_id": inv["_id"]}, {"$set": {"lines": inv["lines"]}})
    # Available supplier credit if the invoice is now over-credited/over-relieved.
    await _recompute_invoice_payment(db, ws, co, inv["_id"])
    refreshed = await get_invoice(db, ws, co, inv["_id"])
    creates_credit = float(refreshed.get("balance") or 0) <= 0.001 and (float(refreshed.get("credited_total") or 0) + float(refreshed.get("amount_paid") or 0)) > float(refreshed.get("total") or 0) + 0.001
    credit_amount = _money(float(refreshed.get("credited_total") or 0) + float(refreshed.get("amount_paid") or 0) - float(refreshed.get("total") or 0)) if creates_credit else 0.0
    if creates_credit:
        await db.ap_supplier_credits.insert_one({
            "_id": f"scr_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co, "supplier_id": inv["supplier_id"],
            "currency": d["currency"], "amount": credit_amount, "remaining": credit_amount,
            "source_credit_note_id": cid, "status": "available", "created_at": _now()})
        await db.ap_suppliers.update_one({"_id": inv["supplier_id"]}, {"$inc": {"credit_balance": credit_amount}})
    await db.ap_credit_notes.update_one({"_id": cid}, {"$set": {
        "status": "posted", "number": number, "journal_entry_id": je["_id"], "posted_by": user.get("id"),
        "posted_at": _now(), "creates_supplier_credit": creates_credit},
        "$push": {"audit": _pay_audit("post", user, "approved", "posted")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


# --------------------------------------------------------------------------- #
# Aging AP + supplier synthetic view (derived from transactions; never stored)
# --------------------------------------------------------------------------- #
def _bucket(as_of, due):
    try:
        days = (datetime.fromisoformat(as_of) - datetime.fromisoformat(due)).days
    except Exception:
        days = 0
    if days <= 0:
        return "current"
    return "d1_30" if days <= 30 else "d31_60" if days <= 60 else "d61_90" if days <= 90 else "d90_plus"


async def aging(db, ws, co, as_of=None):
    """Aging derived from canonical transactions at ``as_of``. Separates the
    accounting AP (posted invoices) from operational commitments (approved but
    not yet posted). Amounts kept per-currency + a functional consolidation."""
    as_of = as_of or _now()[:10]
    functional = await _functional_currency(db, ws, co)
    empty = lambda: {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    accounting = empty()
    approved_unposted = 0.0
    rows = []
    invs = await db.ap_invoices.find({"workspace_id": ws, "company_id": co,
                                      "document_status": "approved"}).to_list(None)
    for inv in invs:
        bal = float(inv.get("balance") or 0)
        if bal <= 0.001:
            continue
        rate = (inv.get("fx") or {}).get("rate", 1.0)
        bal_func = _fx.convert(bal, rate)
        due = inv.get("due_date") or inv.get("invoice_date") or as_of
        if inv.get("posting_status") == "posted":
            bkt = _bucket(as_of, due)
            accounting[bkt] = _money(accounting[bkt] + bal_func)
            rows.append({"invoice_id": inv["_id"], "supplier_id": inv["supplier_id"],
                         "number": inv.get("supplier_invoice_number"), "currency": inv["currency"],
                         "balance": _money(bal), "balance_functional": bal_func, "due_date": due,
                         "bucket": bkt, "kind": "accounting", "journal_entry_id": inv.get("journal_entry_id")})
        else:
            approved_unposted = _money(approved_unposted + bal_func)
            rows.append({"invoice_id": inv["_id"], "supplier_id": inv["supplier_id"],
                         "number": inv.get("supplier_invoice_number"), "currency": inv["currency"],
                         "balance": _money(bal), "balance_functional": bal_func, "due_date": due,
                         "bucket": None, "kind": "approved_unposted", "journal_entry_id": None})
    accounting_total = _money(sum(accounting.values()))
    credits = await db.ap_supplier_credits.find({"workspace_id": ws, "company_id": co, "status": "available"}).to_list(None)
    available_credits = _money(sum(float(c.get("remaining") or 0) for c in credits))
    return {"as_of": as_of, "functional_currency": functional, "buckets": accounting,
            "accounting_total": accounting_total, "approved_unposted": approved_unposted,
            "available_credits": available_credits, "rows": rows}


async def supplier_summary(db, ws, co, supplier_id, as_of=None):
    """Compact supplier KPIs derived from transactions + drill-down anchors."""
    as_of = as_of or _now()[:10]
    functional = await _functional_currency(db, ws, co)
    ag = await aging(db, ws, co, as_of=as_of)
    rows = [r for r in ag["rows"] if r["supplier_id"] == supplier_id]
    buckets = {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    overdue = 0.0
    oldest_due = None
    for r in rows:
        if r["kind"] != "accounting":
            continue
        buckets[r["bucket"]] = _money(buckets[r["bucket"]] + r["balance_functional"])
        if r["bucket"] != "current":
            overdue = _money(overdue + r["balance_functional"])
        if r["due_date"] and (oldest_due is None or r["due_date"] < oldest_due):
            oldest_due = r["due_date"]
    balance = _money(sum(buckets.values()))
    approved_unposted = _money(sum(r["balance_functional"] for r in rows if r["kind"] == "approved_unposted"))
    sup = await db.ap_suppliers.find_one({"_id": supplier_id, "workspace_id": ws, "company_id": co})
    open_count = sum(1 for r in rows if r["kind"] == "accounting")
    recent_pays = await db.ap_payments.find({"workspace_id": ws, "company_id": co, "supplier_id": supplier_id,
        "payment_state": {"$in": ["executed", "posted"]}}).sort("executed_at", -1).to_list(5)
    return {"supplier_id": supplier_id, "functional_currency": functional, "as_of": as_of,
            "balance": balance, "buckets": buckets, "overdue": overdue, "oldest_due_date": oldest_due,
            "approved_unposted": approved_unposted, "open_invoices_count": open_count,
            "available_credits": _money(float((sup or {}).get("credit_balance") or 0)),
            "recent_payments": [public_payment(p) for p in recent_pays]}


# --------------------------------------------------------------------------- #
# Payment batches — PREPARATION object only (never a proof of payment, never GL)
# --------------------------------------------------------------------------- #
_BATCH_STATES = ("draft", "prepared", "authorized", "processing", "completed", "partially_completed", "cancelled")


def public_batch(d):
    if not d:
        return None
    return {"id": d.get("_id"), "state": d.get("state", "draft"), "currency": d.get("currency"),
            "lines": d.get("lines") or [], "snapshot_at": d.get("snapshot_at"),
            "proposed_total": d.get("proposed_total"), "supplier_count": d.get("supplier_count"),
            "invoice_count": d.get("invoice_count"), "note": d.get("note"),
            "created_by": d.get("created_by"), "created_at": d.get("created_at"), "audit": d.get("audit", [])}


async def propose_batch_candidates(db, ws, co, *, currency=None, supplier_id=None, due_before=None):
    """Selectable approved invoices with an open balance (posted or not)."""
    functional = await _functional_currency(db, ws, co)
    q = {"workspace_id": ws, "company_id": co, "document_status": "approved"}
    if supplier_id:
        q["supplier_id"] = supplier_id
    invs = await db.ap_invoices.find(q).sort("due_date", 1).to_list(2000)
    out = []
    for inv in invs:
        bal = float(inv.get("balance") or 0)
        if bal <= 0.001:
            continue
        if currency and (inv.get("currency") or "").upper() != currency.upper():
            continue
        if due_before and (inv.get("due_date") or "9999") > due_before:
            continue
        out.append({"invoice_id": inv["_id"], "supplier_id": inv["supplier_id"],
                    "number": inv.get("supplier_invoice_number"), "currency": inv["currency"],
                    "due_date": inv.get("due_date"), "open_balance": _money(bal),
                    "posting_status": inv.get("posting_status")})
    return {"functional_currency": functional, "candidates": out}


async def create_batch(db, ws, co, user, payload):
    """Freeze a batch snapshot from a selection. No cash out, no GL, no invoice
    mutation. A batch NEVER means the invoices are paid."""
    sel = payload.get("lines") or []
    if not sel:
        raise HTTPException(status_code=422, detail="Sélection vide.")
    lines, total, suppliers, currency = [], 0.0, set(), None
    for rl in sel:
        inv = await get_invoice(db, ws, co, rl["invoice_id"])
        if inv.get("document_status") != "approved":
            raise HTTPException(status_code=409, detail="Seules des factures approuvées peuvent être mises en lot.")
        cur = (inv.get("currency") or "").upper()
        if currency is None:
            currency = cur
        amount = _money(rl.get("amount") if rl.get("amount") is not None else inv.get("balance"))
        open_bal = await _invoice_open_balance(inv)
        if amount <= 0 or amount > open_bal + 0.001:
            raise HTTPException(status_code=422, detail=f"Montant proposé invalide pour {inv.get('supplier_invoice_number') or inv['_id']} (solde {open_bal}).")
        lines.append({"invoice_id": inv["_id"], "supplier_id": inv["supplier_id"],
                      "number": inv.get("supplier_invoice_number"), "currency": cur,
                      "due_date": inv.get("due_date"), "open_balance": open_bal, "proposed_amount": amount})
        total += amount
        suppliers.add(inv["supplier_id"])
    doc = {"_id": f"batch_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co, "state": "draft",
           "currency": currency, "lines": lines, "proposed_total": _money(total),
           "supplier_count": len(suppliers), "invoice_count": len(lines), "note": payload.get("note"),
           "snapshot_at": _now(), "created_by": user.get("id"), "created_at": _now(),
           "audit": [_pay_audit("create", user, None, "draft")]}
    await db.ap_payment_batches.insert_one(doc)
    return public_batch(doc)


async def get_batch(db, ws, co, bid):
    d = await db.ap_payment_batches.find_one({"_id": bid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Lot de paiement introuvable")
    return d


async def list_batches(db, ws, co, *, state=None):
    q = {"workspace_id": ws, "company_id": co}
    if state:
        q["state"] = state
    return [public_batch(d) for d in await db.ap_payment_batches.find(q).sort("created_at", -1).to_list(500)]


async def _batch_transition(db, ws, co, user, bid, allowed_from, to, action):
    d = await get_batch(db, ws, co, bid)
    if d.get("state") not in allowed_from:
        raise HTTPException(status_code=409, detail=f"Transition de lot impossible : « {d.get('state')} ».")
    await db.ap_payment_batches.update_one({"_id": bid}, {"$set": {"state": to},
        "$push": {"audit": _pay_audit(action, user, d.get("state"), to)}})
    return await get_batch(db, ws, co, bid)


async def prepare_batch(db, ws, co, user, bid):
    return public_batch(await _batch_transition(db, ws, co, user, bid, ("draft",), "prepared", "prepare"))


async def authorize_batch(db, ws, co, user, bid):
    return public_batch(await _batch_transition(db, ws, co, user, bid, ("prepared",), "authorized", "authorize"))


async def cancel_batch(db, ws, co, user, bid):
    d = await get_batch(db, ws, co, bid)
    if d.get("state") in ("processing", "completed", "partially_completed"):
        raise HTTPException(status_code=409, detail="Un lot en cours/terminé ne peut être annulé.")
    return public_batch(await _batch_transition(db, ws, co, user, bid, ("draft", "prepared", "authorized"), "cancelled", "cancel"))


async def revalidate_batch(db, ws, co, bid):
    """Re-check each snapshot line against the CURRENT state; surface exceptions
    (invoice no longer approved / balance changed / already paid / supplier
    inactive) without silently mutating the batch."""
    d = await get_batch(db, ws, co, bid)
    exceptions = []
    for ln in d.get("lines") or []:
        inv = await db.ap_invoices.find_one({"_id": ln["invoice_id"], "workspace_id": ws, "company_id": co})
        if not inv:
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "missing"})
            continue
        if inv.get("document_status") != "approved":
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "not_approved", "status": inv.get("document_status")})
        open_bal = await _invoice_open_balance(inv)
        if abs(open_bal - float(ln.get("open_balance") or 0)) > 0.01:
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "balance_changed",
                               "snapshot": ln.get("open_balance"), "current": open_bal})
        if open_bal <= 0.001:
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "already_settled"})
        sup = await db.ap_suppliers.find_one({"_id": inv["supplier_id"], "workspace_id": ws, "company_id": co})
        if (sup or {}).get("status") == "inactive":
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "supplier_inactive"})
        if inv.get("po_required") and not inv.get("purchase_order_id"):
            exceptions.append({"invoice_id": ln["invoice_id"], "issue": "po_missing"})
    return {"batch_id": bid, "ok": len(exceptions) == 0, "exceptions": exceptions}


async def ensure_a43_indexes(db):
    await db.ap_payments.create_index([("workspace_id", 1), ("company_id", 1), ("supplier_id", 1)])
    await db.ap_payments.create_index([("workspace_id", 1), ("company_id", 1), ("allocations.invoice_id", 1)])
    await db.ap_payments.create_index([("workspace_id", 1), ("company_id", 1), ("payment_state", 1)])
    await db.ap_credit_notes.create_index([("workspace_id", 1), ("company_id", 1), ("invoice_id", 1)])
    await db.ap_supplier_credits.create_index([("workspace_id", 1), ("company_id", 1), ("supplier_id", 1)])
    await db.ap_payment_batches.create_index([("workspace_id", 1), ("company_id", 1), ("state", 1)])



# --------------------------------------------------------------------------- #
# A4.3 finition — AP Overview (pilotage compact, dérivé des transactions A4)
# No stored balance, no parallel ledger: every figure is computed on the fly.
# --------------------------------------------------------------------------- #
_TO_PROCESS_STATUSES = ("draft", "verified", "submitted", "po_missing", "discrepancy")


def _days_between(as_of, due):
    try:
        return (datetime.fromisoformat(as_of) - datetime.fromisoformat(due)).days
    except Exception:
        return 0


async def overview(db, ws, co, as_of=None):
    as_of = as_of or _now()[:10]
    functional = await _functional_currency(db, ws, co)

    def add_ccy(bucket, ccy, amount):
        bucket[ccy] = _money(bucket.get(ccy, 0.0) + amount)

    suppliers = {s["_id"]: s for s in await db.ap_suppliers.find(
        {"workspace_id": ws, "company_id": co}).to_list(None)}
    sup_name = lambda sid: (suppliers.get(sid) or {}).get("name") or (sid or "")[:8]

    to_process = 0
    to_pay_func, overdue_func, due7_func = 0.0, 0.0, 0.0
    cash = {"overdue": {}, "d7": {}, "d30": {}, "d30_plus": {}}
    cash_func = {"overdue": 0.0, "d7": 0.0, "d30": 0.0, "d30_plus": 0.0}
    per_supplier = {}
    priorities = []

    invoices = await db.ap_invoices.find({"workspace_id": ws, "company_id": co}).to_list(None)
    for inv in invoices:
        st = inv.get("document_status")
        if st in _TO_PROCESS_STATUSES:
            to_process += 1
            if st == "submitted":
                issue, action = "Approbation requise", "approve"
            elif st == "po_missing":
                issue, action = "PO manquant", "po"
            elif st == "discrepancy":
                issue, action = "Écart détecté", "review"
            else:
                issue, action = "À compléter", "complete"
            priorities.append({"kind": "invoice", "id": inv["_id"], "supplier": sup_name(inv.get("supplier_id")),
                               "supplier_id": inv.get("supplier_id"), "number": inv.get("supplier_invoice_number"),
                               "amount": inv.get("total"), "currency": inv.get("currency"),
                               "due_date": inv.get("due_date"), "issue": issue, "action": action,
                               "urgency": 40, "target": "inbox"})
            continue
        if st != "approved":
            continue
        bal = float(inv.get("balance") or 0)
        if bal <= 0.001:
            continue
        ccy = inv.get("currency") or functional
        rate = (inv.get("fx") or {}).get("rate", 1.0)
        bal_func = _fx.convert(bal, rate)
        to_pay_func += bal_func
        due = inv.get("due_date") or as_of
        days = _days_between(as_of, due)
        if days > 0:
            overdue_func += bal_func
            add_ccy(cash["overdue"], ccy, bal); cash_func["overdue"] += bal_func
        elif days >= -7:
            due7_func += bal_func
            add_ccy(cash["d7"], ccy, bal); cash_func["d7"] += bal_func
        elif days >= -30:
            add_ccy(cash["d30"], ccy, bal); cash_func["d30"] += bal_func
        else:
            add_ccy(cash["d30_plus"], ccy, bal); cash_func["d30_plus"] += bal_func
        s = per_supplier.setdefault(inv["supplier_id"], {"open_func": 0.0, "next_due": None, "ccys": {}})
        s["open_func"] += bal_func
        add_ccy(s["ccys"], ccy, bal)
        if due and (s["next_due"] is None or due < s["next_due"]):
            s["next_due"] = due
        if days > 0:
            priorities.append({"kind": "invoice", "id": inv["_id"], "supplier": sup_name(inv["supplier_id"]),
                               "supplier_id": inv["supplier_id"], "number": inv.get("supplier_invoice_number"),
                               "amount": bal, "currency": ccy, "due_date": due,
                               "issue": f"Échue depuis {days} j", "action": "pay",
                               "urgency": 100 + days, "target": "payments"})

    # Payment lifecycle priorities (prepared/authorized ≠ paid; executed ≠ posted)
    async for p in db.ap_payments.find({"workspace_id": ws, "company_id": co,
                                        "payment_state": {"$in": ["authorized", "executed"]}}):
        if p["payment_state"] == "authorized":
            issue, urg = "Paiement à autoriser", 70
        else:
            issue, urg = "Paiement exécuté à comptabiliser", 60
        priorities.append({"kind": "payment", "id": p["_id"], "supplier": sup_name(p.get("supplier_id")),
                           "supplier_id": p.get("supplier_id"), "number": None, "amount": p.get("amount"),
                           "currency": p.get("currency"), "due_date": p.get("payment_date"),
                           "issue": issue, "action": p["payment_state"], "urgency": urg, "target": "payments"})

    credits = await db.ap_supplier_credits.find({"workspace_id": ws, "company_id": co, "status": "available"}).to_list(None)
    credits_func = _money(sum(_fx.convert(float(c.get("remaining") or 0), 1.0) for c in credits))

    priorities.sort(key=lambda x: x["urgency"], reverse=True)

    top = sorted(({"supplier_id": sid, "name": sup_name(sid), "open_balance": _money(v["open_func"]),
                   "currencies": v["ccys"], "next_due_date": v["next_due"]}
                  for sid, v in per_supplier.items()), key=lambda x: x["open_balance"], reverse=True)[:5]

    return {
        "as_of": as_of, "functional_currency": functional,
        "kpis": {
            "to_process": to_process,
            "to_pay": _money(to_pay_func),
            "overdue": _money(overdue_func),
            "due_7": _money(due7_func),
            "available_credits": credits_func,
        },
        "priorities": priorities[:8],
        "cash": {k: {"by_currency": cash[k], "functional": _money(cash_func[k])} for k in cash},
        "top_suppliers": top,
    }
