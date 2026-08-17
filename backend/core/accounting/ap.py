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
