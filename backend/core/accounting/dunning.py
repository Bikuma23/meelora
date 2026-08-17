"""AR Dunning / Relances — first simple version.

Identify overdue invoices, generate a reminder (PDF stored as a source document),
optionally email it to the customer via Resend, and keep a full history
(actor / date / status / level). No aggressive automatic sending: a reminder is
only produced on an explicit user action.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from ..financial import documents as doc_service
from . import ar_pdf


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return _now()[:10]


async def _company(db, ws, co):
    return await db.companies.find_one({"workspace_id": ws, "$or": [{"id": co}, {"_id": co}]}) or {}


def public_reminder(d):
    return {"id": d.get("_id"), "invoice_id": d.get("invoice_id"), "customer_id": d.get("customer_id"),
            "level": d.get("level"), "status": d.get("status"), "sent_to": d.get("sent_to"),
            "channel": d.get("channel"), "message": d.get("message"), "document_id": d.get("document_id"),
            "sent_at": d.get("sent_at"), "sent_by_email": d.get("sent_by_email"), "error": d.get("error")}


async def overdue_invoices(db, ws, co, as_of=None):
    as_of = as_of or _today()
    invs = await db.sales_invoices.find({"workspace_id": ws, "company_id": co,
                                         "status": {"$in": ["posted", "partially_paid"]}}).to_list(None)
    out = []
    for inv in invs:
        due = inv.get("due_date") or inv.get("issue_date") or as_of
        if float(inv.get("balance") or 0) > 0.001 and as_of > due:
            try:
                days = (datetime.fromisoformat(as_of) - datetime.fromisoformat(due)).days
            except Exception:
                days = 0
            cnt = await db.sales_reminders.count_documents(
                {"workspace_id": ws, "company_id": co, "invoice_id": inv["_id"], "status": "sent"})
            out.append({"invoice_id": inv["_id"], "number": inv.get("number"), "customer_id": inv.get("customer_id"),
                        "currency": inv.get("currency"), "balance": inv.get("balance"), "due_date": due,
                        "days_overdue": days, "reminders_sent": cnt})
    out.sort(key=lambda r: r["days_overdue"], reverse=True)
    return out


async def list_reminders(db, ws, co, *, invoice_id=None):
    q = {"workspace_id": ws, "company_id": co}
    if invoice_id:
        q["invoice_id"] = invoice_id
    docs = await db.sales_reminders.find(q).sort("created_at", -1).to_list(1000)
    return [public_reminder(d) for d in docs]


async def _send_email(to_email, subject, html, pdf_bytes, filename):
    if not os.environ.get("RESEND_API_KEY"):
        return False, "Service courriel non configuré."
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    params = {"from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
              "to": [to_email], "subject": subject, "html": html,
              "attachments": [{"filename": filename, "content": list(pdf_bytes)}]}
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        return True, None
    except Exception as e:
        return False, str(e)


async def create_reminder(db, ws, co, user, payload):
    """Generate a reminder for one overdue invoice, store its PDF as an immutable
    source document, then email it (channel=email) with history."""
    inv = await db.sales_invoices.find_one({"_id": payload["invoice_id"], "workspace_id": ws, "company_id": co})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if inv.get("status") not in ("posted", "partially_paid") or float(inv.get("balance") or 0) <= 0.001:
        raise HTTPException(status_code=409, detail="Seule une facture comptabilisée avec un solde dû peut faire l'objet d'une relance.")
    cust = await db.sales_customers.find_one({"_id": inv["customer_id"], "workspace_id": ws, "company_id": co}) or {}
    to_email = payload.get("to_email") or cust.get("billing_email") or (cust.get("emails") or [None])[0]
    channel = payload.get("channel") or "email"
    if channel == "email" and not to_email:
        raise HTTPException(status_code=422, detail="Aucun courriel de facturation pour ce client.")
    sent = await db.sales_reminders.count_documents(
        {"workspace_id": ws, "company_id": co, "invoice_id": inv["_id"], "status": "sent"})
    level = int(payload.get("level") or (sent + 1))
    company = await _company(db, ws, co)
    inv_pub = {**inv, "id": inv["_id"]}
    message = payload.get("message") or ""
    logo_bytes, accent = await doc_service.company_branding_assets(db, ws, co, company)
    pdf = ar_pdf.build_reminder_pdf(company=company, customer=cust, invoice=inv_pub, level=level, message=message,
                                    logo_bytes=logo_bytes, accent=accent)
    stored = await doc_service.store_document(
        db, ws, co, user, source_type="ar_reminder", source_id=inv["_id"], data=pdf,
        filename=f"relance_{inv.get('number') or inv['_id']}_n{level}.pdf", kind="reminder",
        meta={"level": level, "invoice_number": inv.get("number")})
    rid = f"rem_{uuid.uuid4().hex}"
    status, error = "generated", None
    if channel == "email":
        subject = f"Rappel de paiement — Facture {inv.get('number') or ''}".strip()
        html = (f"<p>Bonjour {cust.get('name') or ''},</p>"
                f"<p>{message or 'Nous vous rappelons que la facture ci-jointe présente un solde dû.'}</p>"
                f"<p>Facture <b>{inv.get('number') or ''}</b> — solde dû "
                f"<b>{float(inv.get('balance') or 0):,.2f} {inv.get('currency') or ''}</b>.</p>"
                f"<p>Cordialement,<br/>{company.get('name') or ''}</p>")
        ok, error = await _send_email(to_email, subject, html, pdf, f"relance_{inv.get('number') or inv['_id']}.pdf")
        status = "sent" if ok else "failed"
    doc = {"_id": rid, "workspace_id": ws, "company_id": co, "invoice_id": inv["_id"],
           "customer_id": inv["customer_id"], "level": level, "channel": channel, "status": status,
           "sent_to": to_email if channel == "email" else None, "message": message, "document_id": stored["id"],
           "error": error, "sent_at": _now() if status == "sent" else None,
           "sent_by": user.get("id"), "sent_by_email": user.get("email"), "created_at": _now()}
    await db.sales_reminders.insert_one(doc)
    return public_reminder(doc)
