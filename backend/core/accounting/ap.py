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
    "recoverable_tax_account_code": "TAX_RECOVERABLE",
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

