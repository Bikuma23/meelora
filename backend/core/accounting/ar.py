"""ACCOUNTING A3 — Accounts Receivable (Ventes & Clients).

Operational AR workflow layered on the Financial Core P2 (canonical periods P2.2,
canonical journal P2.6, accounts P2.3) and the shared FX + tax engines. This is
NOT a second ledger: every posting creates ONE canonical journal entry via the A2
helper. Legacy acct_*/qc9434_* are never touched.

Three DISTINCT concepts (never conflated in the data model):
  * VOID / full reversal  — cancels a posted, unpaid invoice with a linked mirror
    journal entry (invoice is never mutated).
  * CREDIT NOTE           — an autonomous AR document (own number + workflow) that
    commercially credits all/part of an invoice, reusing the ORIGINAL tax + FX
    snapshot; reduces AR, or becomes available customer credit if already paid.
  * REFUND (monetary)     — modelled as consuming an available customer credit;
    the full cash-out workflow is deferred beyond A3.

Multi-currency by design: invoice keeps its transaction currency + an immutable FX
snapshot; the journal is always balanced in the company functional currency;
payments at a different rate realise an FX gain/loss.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from ..financial import journal as journal_service
from ..financial import fx as fx_service
from ..financial import tax_engine
from .gl import _assert_postable_period, _get_period

INVOICE_STATUSES = ("draft", "submitted", "approved", "posted", "partially_paid", "paid", "void")
CREDIT_STATUSES = ("draft", "submitted", "approved", "posted")

_DEFAULT_MAPPING = {
    "ar_account_code": "AR", "bank_account_code": "BANK",
    "default_revenue_account_code": "REVENUE",
    "fx_gain_account_code": "FX_GAIN", "fx_loss_account_code": "FX_LOSS",
    "rounding_account_code": "ROUNDING",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _money(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Montant invalide")


def _audit(action, user, frm, to):
    return {"action": action, "by": user.get("id"), "by_email": user.get("email"),
            "at": _now(), "from_status": frm, "to_status": to}


async def _functional_currency(db, workspace_id, company_id):
    c = await db.companies.find_one({"workspace_id": workspace_id, "$or": [{"id": company_id}, {"_id": company_id}]})
    return ((c or {}).get("functional_currency") or "CAD").upper()


# --------------------------------------------------------------------------- #
# GL mapping (account codes) — admin-configurable
# --------------------------------------------------------------------------- #
async def get_mapping(db, workspace_id, company_id):
    d = await db.sales_gl_mapping.find_one({"workspace_id": workspace_id, "company_id": company_id})
    merged = {**_DEFAULT_MAPPING, **{k: v for k, v in (d or {}).items() if k in _DEFAULT_MAPPING and v}}
    merged["workspace_id"], merged["company_id"] = workspace_id, company_id
    return merged


async def set_mapping(db, workspace_id, company_id, payload):
    changes = {k: v for k, v in payload.items() if k in _DEFAULT_MAPPING and v}
    await db.sales_gl_mapping.update_one(
        {"workspace_id": workspace_id, "company_id": company_id},
        {"$set": {**changes, "updated_at": _now()}}, upsert=True)
    return await get_mapping(db, workspace_id, company_id)


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
def public_customer(d):
    return {"id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
            "code": d.get("code"), "name": d.get("name"), "emails": d.get("emails", []),
            "billing_address": d.get("billing_address"), "tax_ids": d.get("tax_ids", {}),
            "default_tax_code": d.get("default_tax_code"), "default_currency": d.get("default_currency"),
            "default_revenue_account_code": d.get("default_revenue_account_code"),
            "status": d.get("status", "active"), "credit_balance": d.get("credit_balance", 0.0)}


async def list_customers(db, workspace_id, company_id):
    docs = await db.sales_customers.find({"workspace_id": workspace_id, "company_id": company_id}).sort("name", 1).to_list(1000)
    return [public_customer(d) for d in docs]


async def get_customer(db, workspace_id, company_id, customer_id):
    d = await db.sales_customers.find_one({"_id": customer_id, "workspace_id": workspace_id, "company_id": company_id})
    if not d:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return d


async def create_customer(db, workspace_id, company_id, user, payload):
    if not payload.get("name"):
        raise HTTPException(status_code=422, detail="Nom du client requis")
    doc = {"_id": f"cust_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "code": payload.get("code") or "", "name": payload["name"].strip(),
           "emails": payload.get("emails") or [], "billing_address": payload.get("billing_address"),
           "tax_ids": payload.get("tax_ids") or {}, "default_tax_code": payload.get("default_tax_code"),
           "default_currency": (payload.get("default_currency") or await _functional_currency(db, workspace_id, company_id)).upper(),
           "default_revenue_account_code": payload.get("default_revenue_account_code"),
           "status": "active", "credit_balance": 0.0, "created_at": _now(), "created_by": user.get("id")}
    await db.sales_customers.insert_one(doc)
    return public_customer(doc)


async def update_customer(db, workspace_id, company_id, user, customer_id, payload):
    await get_customer(db, workspace_id, company_id, customer_id)
    changes = {k: v for k, v in payload.items() if k in (
        "code", "name", "emails", "billing_address", "tax_ids", "default_tax_code",
        "default_currency", "default_revenue_account_code", "status") and v is not None}
    if "default_currency" in changes:
        changes["default_currency"] = changes["default_currency"].upper()
    if changes:
        await db.sales_customers.update_one({"_id": customer_id}, {"$set": {**changes, "updated_at": _now()}})
    return public_customer(await get_customer(db, workspace_id, company_id, customer_id))


# --------------------------------------------------------------------------- #
# Sequences
# --------------------------------------------------------------------------- #
async def _next_number(db, workspace_id, company_id, kind, year):
    key = f"{workspace_id}:{company_id}:{kind}:{year}"
    doc = await db.sales_sequences.find_one_and_update(
        {"_id": key}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    seq = (doc or {}).get("seq", 1)
    return f"{kind}-{year}-{seq:04d}"


# --------------------------------------------------------------------------- #
# Invoice compute + snapshot
# --------------------------------------------------------------------------- #
async def _resolve_fx(db, workspace_id, company_id, currency, functional, on_date, provided_rate=None):
    """Immutable FX snapshot (transaction currency -> functional)."""
    currency = (currency or functional).upper()
    if currency == functional:
        return {"from_currency": currency, "to_currency": functional, "rate": 1.0,
                "rate_date": on_date, "source": "identity"}
    if provided_rate:
        return {"from_currency": currency, "to_currency": functional, "rate": float(provided_rate),
                "rate_date": on_date, "source": "provided"}
    r = await fx_service.get_rate(db, workspace_id, company_id, from_currency=currency, to_currency=functional, on_date=on_date)
    if not r:
        raise HTTPException(status_code=422, detail=f"Taux de change requis {currency}->{functional} au {on_date}.")
    return {"from_currency": currency, "to_currency": functional, "rate": r["rate"],
            "rate_date": r["rate_date"], "source": r["source"]}


async def _compute_lines(db, workspace_id, company_id, lines, on_date, default_revenue):
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
            tax_cache[code] = await tax_engine.get_tax_code(db, workspace_id, company_id, code)
        snap = tax_engine.compute_line_tax(tax_cache[code], net, on_date)
        subtotal += net
        tax_total += snap["tax_total"]
        out.append({"description": ln.get("description", ""), "qty": qty, "unit_price": unit,
                    "revenue_account_code": ln.get("revenue_account_code") or default_revenue,
                    "line_net": net, "tax": snap, "tax_amount": snap["tax_total"], "credited_net": 0.0})
    subtotal, tax_total = _money(subtotal), _money(tax_total)
    return out, subtotal, tax_total, _money(subtotal + tax_total)


def public_invoice(d):
    return {"id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
            "number": d.get("number"), "customer_id": d.get("customer_id"), "status": d.get("status", "draft"),
            "currency": d.get("currency"), "fx": d.get("fx"), "issue_date": d.get("issue_date"),
            "due_date": d.get("due_date"), "period_id": d.get("period_id"),
            "financial_period_id": d.get("financial_period_id"), "financial_year_id": d.get("financial_year_id"),
            "lines": d.get("lines", []), "subtotal": d.get("subtotal"), "tax_total": d.get("tax_total"),
            "total": d.get("total"), "amount_paid": d.get("amount_paid", 0.0),
            "credited_total": d.get("credited_total", 0.0), "balance": d.get("balance"),
            "journal_entry_id": d.get("journal_entry_id"), "reversal_journal_entry_id": d.get("reversal_journal_entry_id"),
            "created_by": d.get("created_by"), "approved_by": d.get("approved_by"),
            "posted_by": d.get("posted_by"), "audit": d.get("audit", [])}


async def get_invoice(db, workspace_id, company_id, invoice_id):
    d = await db.sales_invoices.find_one({"_id": invoice_id, "workspace_id": workspace_id, "company_id": company_id})
    if not d:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return d


async def list_invoices(db, workspace_id, company_id, *, status=None, customer_id=None):
    q = {"workspace_id": workspace_id, "company_id": company_id}
    if status:
        q["status"] = status
    if customer_id:
        q["customer_id"] = customer_id
    docs = await db.sales_invoices.find(q).sort("created_at", -1).to_list(1000)
    return [public_invoice(d) for d in docs]


async def create_invoice(db, workspace_id, company_id, user, payload):
    functional = await _functional_currency(db, workspace_id, company_id)
    customer = await get_customer(db, workspace_id, company_id, payload["customer_id"])
    period = await _get_period(db, workspace_id, company_id, payload["period_id"])
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée : création impossible.")
    currency = (payload.get("currency") or customer.get("default_currency") or functional).upper()
    issue_date = payload.get("issue_date") or _now()[:10]
    mapping = await get_mapping(db, workspace_id, company_id)
    default_rev = customer.get("default_revenue_account_code") or mapping["default_revenue_account_code"]
    lines, subtotal, tax_total, total = await _compute_lines(
        db, workspace_id, company_id, payload.get("lines"), issue_date, default_rev)
    fx = await _resolve_fx(db, workspace_id, company_id, currency, functional, issue_date, payload.get("fx_rate"))
    doc = {"_id": f"inv_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "number": None, "customer_id": customer["_id"], "status": "draft", "currency": currency, "fx": fx,
           "issue_date": issue_date, "due_date": payload.get("due_date"),
           "period_id": period["_id"], "financial_period_id": period["_id"],
           "financial_year_id": period.get("financial_year_id"),
           "lines": lines, "subtotal": subtotal, "tax_total": tax_total, "total": total,
           "amount_paid": 0.0, "credited_total": 0.0, "balance": total,
           "created_by": user.get("id"), "created_at": _now(), "audit": [_audit("create", user, None, "draft")]}
    await db.sales_invoices.insert_one(doc)
    return public_invoice(doc)


async def _require_invoice_status(db, ws, co, invoice_id, expected):
    d = await get_invoice(db, ws, co, invoice_id)
    if d.get("status") != expected:
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    return d


async def update_invoice_draft(db, ws, co, user, invoice_id, payload):
    d = await _require_invoice_status(db, ws, co, invoice_id, "draft")
    functional = await _functional_currency(db, ws, co)
    changes = {}
    currency = (payload.get("currency") or d["currency"]).upper()
    issue_date = payload.get("issue_date") or d["issue_date"]
    if payload.get("lines") is not None:
        customer = await get_customer(db, ws, co, d["customer_id"])
        mapping = await get_mapping(db, ws, co)
        default_rev = customer.get("default_revenue_account_code") or mapping["default_revenue_account_code"]
        lines, subtotal, tax_total, total = await _compute_lines(db, ws, co, payload["lines"], issue_date, default_rev)
        changes.update({"lines": lines, "subtotal": subtotal, "tax_total": tax_total, "total": total, "balance": total})
    for f in ("due_date",):
        if payload.get(f) is not None:
            changes[f] = payload[f]
    if payload.get("currency") or payload.get("issue_date") or payload.get("fx_rate") is not None:
        changes["currency"] = currency
        changes["issue_date"] = issue_date
        changes["fx"] = await _resolve_fx(db, ws, co, currency, functional, issue_date, payload.get("fx_rate"))
    if changes:
        await db.sales_invoices.update_one({"_id": invoice_id}, {"$set": changes, "$push": {"audit": _audit("update", user, "draft", "draft")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def submit_invoice(db, ws, co, user, invoice_id):
    d = await _require_invoice_status(db, ws, co, invoice_id, "draft")
    if not d.get("lines"):
        raise HTTPException(status_code=422, detail="Facture vide.")
    await db.sales_invoices.update_one({"_id": invoice_id}, {
        "$set": {"status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _audit("submit", user, "draft", "submitted")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def approve_invoice(db, ws, co, user, invoice_id):
    d = await _require_invoice_status(db, ws, co, invoice_id, "submitted")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403, detail="Séparation des tâches : le créateur ne peut pas approuver sa facture.")
    await db.sales_invoices.update_one({"_id": invoice_id}, {
        "$set": {"status": "approved", "approved_by": user.get("id")},
        "$push": {"audit": _audit("approve", user, "submitted", "approved")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def post_invoice(db, ws, co, user, invoice_id):
    d = await get_invoice(db, ws, co, invoice_id)
    if d.get("status") in ("posted", "partially_paid", "paid") and d.get("journal_entry_id"):
        return public_invoice(d)  # idempotent
    if d.get("status") != "approved":
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    period = await _get_period(db, ws, co, d["period_id"])
    await _assert_postable_period(db, ws, co, period)
    mapping = await get_mapping(db, ws, co)
    rate = d["fx"]["rate"]
    gl_lines, credits_func = [], 0.0
    for ln in d["lines"]:
        net_func = fx_service.convert(ln["line_net"], rate)
        if net_func:
            gl_lines.append({"account": ln["revenue_account_code"], "description": ln.get("description") or "Produit",
                             "debit": 0, "credit": net_func, "txn_credit": ln["line_net"], "txn_currency": d["currency"]})
            credits_func += net_func
        for comp in ln["tax"]["components"]:
            amt_func = fx_service.convert(comp["amount"], rate)
            if amt_func:
                gl_lines.append({"account": comp["payable_account_code"], "description": f"{comp['name']} sur vente",
                                 "debit": 0, "credit": amt_func, "txn_credit": comp["amount"], "txn_currency": d["currency"]})
                credits_func += amt_func
    ar_func = _money(credits_func)
    gl_lines.insert(0, {"account": mapping["ar_account_code"], "description": "Comptes clients",
                        "debit": ar_func, "credit": 0, "txn_debit": d["total"], "txn_currency": d["currency"]})
    number = await _next_number(db, ws, co, "INV", (d["issue_date"] or _now())[:4])
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=d["issue_date"], reference=number, description=f"Facture {number}",
        lines=gl_lines, external_id=invoice_id, source_type="invoice", source_system="sales",
        transaction_currency=d["currency"], fx=d["fx"])
    await db.sales_invoices.update_one({"_id": invoice_id}, {
        "$set": {"status": "posted", "number": number, "posted_by": user.get("id"), "posted_at": _now(),
                 "journal_entry_id": je["_id"]},
        "$push": {"audit": _audit("post", user, "approved", "posted")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


async def void_invoice(db, ws, co, user, invoice_id):
    """Full reversal (VOID) — only a posted, UNPAID, UN-credited invoice. Creates a
    linked mirror journal entry; the original invoice/journal is never mutated."""
    d = await get_invoice(db, ws, co, invoice_id)
    if d.get("status") not in ("posted",):
        raise HTTPException(status_code=409, detail="Seule une facture comptabilisée (non payée/non créditée) peut être extournée.")
    if d.get("amount_paid", 0) > 0:
        raise HTTPException(status_code=409, detail="Facture partiellement/entièrement payée : utilisez une note de crédit.")
    if d.get("credited_total", 0) > 0:
        raise HTTPException(status_code=409, detail="Facture déjà créditée : utilisez une note de crédit.")
    period = await _get_period(db, ws, co, d["period_id"])
    await _assert_postable_period(db, ws, co, period)
    orig_je = await db.journal_entries.find_one({"_id": d["journal_entry_id"]})
    orig_lines = await db.journal_entry_lines.find({"journal_entry_id": d["journal_entry_id"]}).sort("line_number", 1).to_list(None)
    rev_lines = [{"account": l["account_code"], "description": f"Extourne — {l.get('description') or ''}".strip(),
                  "debit": l.get("credit", 0), "credit": l.get("debit", 0),
                  "txn_debit": l.get("txn_credit"), "txn_credit": l.get("txn_debit"), "txn_currency": l.get("txn_currency")}
                 for l in orig_lines]
    ref = f"VOID-{d.get('number') or invoice_id}"
    rev_je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=_now()[:10], reference=ref, description=f"Extourne facture {d.get('number')}",
        lines=rev_lines, external_id=f"void_{invoice_id}", source_type="invoice", source_system="sales",
        reverses_journal_entry_id=d["journal_entry_id"], transaction_currency=d["currency"], fx=d["fx"])
    await journal_service.link_reversal(db, ws, co, d["journal_entry_id"], rev_je["_id"])
    await db.sales_invoices.update_one({"_id": invoice_id}, {
        "$set": {"status": "void", "balance": 0.0, "reversal_journal_entry_id": rev_je["_id"]},
        "$push": {"audit": _audit("void", user, "posted", "void")}})
    return public_invoice(await get_invoice(db, ws, co, invoice_id))


# --------------------------------------------------------------------------- #
# Payments (with realised FX gain/loss)
# --------------------------------------------------------------------------- #
def public_payment(d):
    return {"id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
            "invoice_id": d.get("invoice_id"), "customer_id": d.get("customer_id"), "date": d.get("date"),
            "amount": d.get("amount"), "currency": d.get("currency"), "method": d.get("method"),
            "fx": d.get("fx"), "realized_fx": d.get("realized_fx", 0.0), "status": d.get("status"),
            "journal_entry_id": d.get("journal_entry_id"), "created_by": d.get("created_by")}


async def create_payment(db, ws, co, user, payload):
    """Record + post a customer payment against a posted invoice. Dr Bank /
    Cr AR (at invoice rate) with a realised FX gain/loss when the payment rate
    differs from the invoice rate."""
    inv = await get_invoice(db, ws, co, payload["invoice_id"])
    if inv.get("status") not in ("posted", "partially_paid"):
        raise HTTPException(status_code=409, detail="La facture doit être comptabilisée pour être encaissée.")
    functional = await _functional_currency(db, ws, co)
    amount = _money(payload.get("amount"))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Montant d'encaissement invalide.")
    if amount > inv["balance"] + 0.001:
        raise HTTPException(status_code=422, detail=f"Encaissement ({amount}) supérieur au solde dû ({inv['balance']}).")
    pay_currency = (payload.get("currency") or inv["currency"]).upper()
    if pay_currency != inv["currency"]:
        raise HTTPException(status_code=422, detail="A3 : encaissement dans la devise de la facture uniquement.")
    date = payload.get("date") or _now()[:10]
    period = await _get_period(db, ws, co, payload.get("period_id") or inv["period_id"])
    await _assert_postable_period(db, ws, co, period)
    pay_fx = await _resolve_fx(db, ws, co, pay_currency, functional, date, payload.get("fx_rate"))
    mapping = await get_mapping(db, ws, co)
    bank_func = fx_service.convert(amount, pay_fx["rate"])
    ar_func = fx_service.convert(amount, inv["fx"]["rate"])  # AR relieved at ORIGINAL invoice rate
    diff = round(bank_func - ar_func, 2)  # >0 gain, <0 loss
    gl = [{"account": mapping["bank_account_code"], "description": "Encaissement client",
           "debit": bank_func, "credit": 0, "txn_debit": amount, "txn_currency": pay_currency},
          {"account": mapping["ar_account_code"], "description": "Règlement facture",
           "debit": 0, "credit": ar_func, "txn_credit": amount, "txn_currency": inv["currency"]}]
    if diff > 0:
        gl.append({"account": mapping["fx_gain_account_code"], "description": "Gain de change réalisé", "debit": 0, "credit": diff})
    elif diff < 0:
        gl.append({"account": mapping["fx_loss_account_code"], "description": "Perte de change réalisée", "debit": -diff, "credit": 0})
    pid = f"pay_{uuid.uuid4().hex}"
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=period.get("financial_year_id"), financial_period_id=period["_id"],
        entry_date=date, reference=f"PAY-{inv.get('number') or inv['_id']}",
        description=f"Encaissement facture {inv.get('number')}", lines=gl, external_id=pid,
        source_type="manual", source_system="sales", transaction_currency=pay_currency, fx=pay_fx)
    new_paid = _money(inv["amount_paid"] + amount)
    new_balance = _money(inv["total"] - inv.get("credited_total", 0) - new_paid)
    new_status = "paid" if new_balance <= 0.001 else "partially_paid"
    await db.sales_invoices.update_one({"_id": inv["_id"]}, {
        "$set": {"amount_paid": new_paid, "balance": max(new_balance, 0.0), "status": new_status},
        "$push": {"audit": _audit("payment", user, inv["status"], new_status)}})
    doc = {"_id": pid, "workspace_id": ws, "company_id": co, "invoice_id": inv["_id"], "customer_id": inv["customer_id"],
           "date": date, "amount": amount, "currency": pay_currency, "method": payload.get("method") or "bank",
           "fx": pay_fx, "realized_fx": diff, "financial_period_id": period["_id"],
           "journal_entry_id": je["_id"], "status": "posted", "created_by": user.get("id"), "created_at": _now()}
    await db.sales_payments.insert_one(doc)
    return public_payment(doc)


async def list_payments(db, ws, co, *, invoice_id=None):
    q = {"workspace_id": ws, "company_id": co}
    if invoice_id:
        q["invoice_id"] = invoice_id
    return [public_payment(d) for d in await db.sales_payments.find(q).sort("created_at", -1).to_list(1000)]


# --------------------------------------------------------------------------- #
# Credit notes (full / partial) — autonomous AR documents
# --------------------------------------------------------------------------- #
def public_credit_note(d):
    return {"id": d.get("_id"), "workspace_id": d.get("workspace_id"), "company_id": d.get("company_id"),
            "number": d.get("number"), "invoice_id": d.get("invoice_id"), "customer_id": d.get("customer_id"),
            "status": d.get("status", "draft"), "currency": d.get("currency"), "fx": d.get("fx"),
            "lines": d.get("lines", []), "subtotal": d.get("subtotal"), "tax_total": d.get("tax_total"),
            "total": d.get("total"), "period_id": d.get("period_id"), "financial_year_id": d.get("financial_year_id"),
            "journal_entry_id": d.get("journal_entry_id"), "created_by": d.get("created_by"),
            "approved_by": d.get("approved_by"), "posted_by": d.get("posted_by"),
            "creates_customer_credit": d.get("creates_customer_credit", False), "audit": d.get("audit", [])}


async def get_credit_note(db, ws, co, cid):
    d = await db.sales_credit_notes.find_one({"_id": cid, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Note de crédit introuvable")
    return d


async def list_credit_notes(db, ws, co, *, invoice_id=None, status=None):
    q = {"workspace_id": ws, "company_id": co}
    if invoice_id:
        q["invoice_id"] = invoice_id
    if status:
        q["status"] = status
    return [public_credit_note(d) for d in await db.sales_credit_notes.find(q).sort("created_at", -1).to_list(1000)]


async def create_credit_note(db, ws, co, user, payload):
    """Autonomous AR credit document against a posted invoice. Reuses the ORIGINAL
    invoice tax + FX snapshot (never recomputes with current rates). Guards against
    over-crediting per invoice line."""
    inv = await get_invoice(db, ws, co, payload["invoice_id"])
    if inv.get("status") not in ("posted", "partially_paid", "paid"):
        raise HTTPException(status_code=409, detail="Note de crédit possible seulement sur une facture comptabilisée.")
    req_lines = payload.get("lines") or []
    if not req_lines:
        raise HTTPException(status_code=422, detail="Au moins une ligne à créditer est requise.")
    period = await _get_period(db, ws, co, payload.get("period_id") or inv["period_id"])
    if period.get("status") == "closed":
        raise HTTPException(status_code=409, detail="Période clôturée.")
    out_lines, subtotal, tax_total = [], 0.0, 0.0
    for rl in req_lines:
        idx = int(rl.get("invoice_line_index"))
        if idx < 0 or idx >= len(inv["lines"]):
            raise HTTPException(status_code=422, detail="Ligne de facture invalide.")
        src = inv["lines"][idx]
        credit_net = _money(rl.get("net_credit"))
        remaining = _money(src["line_net"] - src.get("credited_net", 0.0))
        if credit_net <= 0:
            raise HTTPException(status_code=422, detail="Montant à créditer invalide.")
        if credit_net > remaining + 0.001:
            raise HTTPException(status_code=422, detail=f"Sur-crédit interdit (ligne {idx}) : restant {remaining}.")
        # Tax credited proportionally to the ORIGINAL line tax snapshot (same rates).
        ratio = (credit_net / src["line_net"]) if src["line_net"] else 0
        comps = [{"name": c["name"], "tax_type": c["tax_type"], "rate": c["rate"],
                  "payable_account_code": c["payable_account_code"], "amount": _money(c["amount"] * ratio)}
                 for c in src["tax"]["components"]]
        line_tax = _money(sum(c["amount"] for c in comps))
        subtotal += credit_net
        tax_total += line_tax
        out_lines.append({"invoice_line_index": idx, "description": src.get("description", ""),
                          "revenue_account_code": src["revenue_account_code"], "net_credit": credit_net,
                          "tax": {"components": comps, "tax_total": line_tax}})
    subtotal, tax_total = _money(subtotal), _money(tax_total)
    doc = {"_id": f"cn_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co, "number": None,
           "invoice_id": inv["_id"], "customer_id": inv["customer_id"], "status": "draft",
           "currency": inv["currency"], "fx": inv["fx"], "lines": out_lines,
           "subtotal": subtotal, "tax_total": tax_total, "total": _money(subtotal + tax_total),
           "period_id": period["_id"], "financial_period_id": period["_id"],
           "financial_year_id": period.get("financial_year_id"),
           "created_by": user.get("id"), "created_at": _now(), "audit": [_audit("create", user, None, "draft")]}
    await db.sales_credit_notes.insert_one(doc)
    return public_credit_note(doc)


async def _require_cn_status(db, ws, co, cid, expected):
    d = await get_credit_note(db, ws, co, cid)
    if d.get("status") != expected:
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    return d


async def submit_credit_note(db, ws, co, user, cid):
    await _require_cn_status(db, ws, co, cid, "draft")
    await db.sales_credit_notes.update_one({"_id": cid}, {
        "$set": {"status": "submitted", "submitted_by": user.get("id")},
        "$push": {"audit": _audit("submit", user, "draft", "submitted")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


async def approve_credit_note(db, ws, co, user, cid):
    d = await _require_cn_status(db, ws, co, cid, "submitted")
    if d.get("created_by") == user.get("id"):
        raise HTTPException(status_code=403, detail="Séparation des tâches : le créateur ne peut pas approuver la note de crédit.")
    await db.sales_credit_notes.update_one({"_id": cid}, {
        "$set": {"status": "approved", "approved_by": user.get("id")},
        "$push": {"audit": _audit("approve", user, "submitted", "approved")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


async def post_credit_note(db, ws, co, user, cid):
    d = await get_credit_note(db, ws, co, cid)
    if d.get("status") == "posted" and d.get("journal_entry_id"):
        return public_credit_note(d)  # idempotent
    if d.get("status") != "approved":
        raise HTTPException(status_code=409, detail=f"Transition impossible : statut « {d.get('status')} ».")
    period = await _get_period(db, ws, co, d["period_id"])
    await _assert_postable_period(db, ws, co, period)
    inv = await get_invoice(db, ws, co, d["invoice_id"])
    mapping = await get_mapping(db, ws, co)
    rate = d["fx"]["rate"]  # ORIGINAL invoice rate
    gl, debits_func = [], 0.0
    for ln in d["lines"]:
        net_func = fx_service.convert(ln["net_credit"], rate)
        if net_func:
            gl.append({"account": ln["revenue_account_code"], "description": "Crédit produit",
                       "debit": net_func, "credit": 0, "txn_debit": ln["net_credit"], "txn_currency": d["currency"]})
            debits_func += net_func
        for c in ln["tax"]["components"]:
            amt_func = fx_service.convert(c["amount"], rate)
            if amt_func:
                gl.append({"account": c["payable_account_code"], "description": f"Crédit {c['name']}",
                           "debit": amt_func, "credit": 0, "txn_debit": c["amount"], "txn_currency": d["currency"]})
                debits_func += amt_func
    ar_func = _money(debits_func)
    gl.append({"account": mapping["ar_account_code"], "description": "Réduction comptes clients",
               "debit": 0, "credit": ar_func, "txn_credit": d["total"], "txn_currency": d["currency"]})
    number = await _next_number(db, ws, co, "CN", _now()[:4])
    je = await journal_service.create_workflow_journal_entry(
        db, ws, co, user, financial_year_id=d.get("financial_year_id"), financial_period_id=d["period_id"],
        entry_date=_now()[:10], reference=number, description=f"Note de crédit {number} (facture {inv.get('number')})",
        lines=gl, external_id=cid, source_type="invoice", source_system="sales",
        transaction_currency=d["currency"], fx=d["fx"])
    # Update invoice: increment per-line credited_net + totals, recompute balance.
    for ln in d["lines"]:
        inv["lines"][ln["invoice_line_index"]]["credited_net"] = _money(
            inv["lines"][ln["invoice_line_index"]].get("credited_net", 0.0) + ln["net_credit"])
    new_credited = _money(inv.get("credited_total", 0.0) + d["total"])
    net_billed = _money(inv["total"] - new_credited)
    new_balance = _money(net_billed - inv.get("amount_paid", 0.0))
    creates_credit = new_balance < -0.001  # already over-paid -> available customer credit
    credit_amount = _money(-new_balance) if creates_credit else 0.0
    await db.sales_invoices.update_one({"_id": inv["_id"]}, {
        "$set": {"lines": inv["lines"], "credited_total": new_credited, "balance": max(new_balance, 0.0),
                 "status": ("paid" if new_balance <= 0.001 and inv.get("amount_paid", 0) > 0 else inv["status"])}})
    if creates_credit:
        await db.sales_customer_credits.insert_one({
            "_id": f"ccr_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
            "customer_id": inv["customer_id"], "currency": d["currency"], "amount": credit_amount,
            "remaining": credit_amount, "source_credit_note_id": cid, "status": "available", "created_at": _now()})
        await db.sales_customers.update_one({"_id": inv["customer_id"]},
                                            {"$inc": {"credit_balance": credit_amount}})
    await db.sales_credit_notes.update_one({"_id": cid}, {
        "$set": {"status": "posted", "number": number, "posted_by": user.get("id"), "posted_at": _now(),
                 "journal_entry_id": je["_id"], "creates_customer_credit": creates_credit},
        "$push": {"audit": _audit("post", user, "approved", "posted")}})
    return public_credit_note(await get_credit_note(db, ws, co, cid))


# --------------------------------------------------------------------------- #
# Aging (functional currency; original amounts retained on documents)
# --------------------------------------------------------------------------- #
async def aging(db, ws, co, as_of=None):
    as_of = as_of or _now()[:10]
    functional = await _functional_currency(db, ws, co)
    invoices = await db.sales_invoices.find({"workspace_id": ws, "company_id": co,
                                             "status": {"$in": ["posted", "partially_paid"]}}).to_list(None)
    buckets = {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    rows = []
    for inv in invoices:
        bal_func = fx_service.convert(inv.get("balance", 0), inv["fx"]["rate"])
        if bal_func <= 0:
            continue
        due = inv.get("due_date") or inv.get("issue_date") or as_of
        overdue = (as_of > due)
        days = 0
        try:
            days = (datetime.fromisoformat(as_of) - datetime.fromisoformat(due)).days if overdue else 0
        except Exception:
            days = 0
        bkt = "current" if not overdue else ("d1_30" if days <= 30 else "d31_60" if days <= 60 else "d61_90" if days <= 90 else "d90_plus")
        buckets[bkt] = _money(buckets[bkt] + bal_func)
        rows.append({"invoice_id": inv["_id"], "number": inv.get("number"), "customer_id": inv["customer_id"],
                     "currency": inv["currency"], "balance": inv.get("balance"), "balance_functional": bal_func,
                     "due_date": due, "bucket": bkt})
    return {"as_of": as_of, "functional_currency": functional, "buckets": buckets, "rows": rows}
