"""A3 — Document Service (immutable source docs) + journal->source traceability +
enriched customer referential + dunning/relances. Standalone runner (exit 0 = pass).
Throwaway workspace; no legacy touched.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.accounting import ar, dunning
from core.financial import tax_engine, documents as docs

WS = "ws_a3docs_test"
_fail = []


def ok(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fail.append(name)


async def _seed(db, co):
    await db.companies.insert_one({"_id": co, "workspace_id": WS, "name": "Test Co", "functional_currency": "CHF",
                                   "jurisdiction": "CH", "address": "Rue 1, Genève", "tax_ids": {"TVA": "CHE-123"}})
    await db.financial_years.insert_one({"_id": f"fy_{co}", "workspace_id": WS, "company_id": co, "label": "2026",
                                         "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"})
    p1 = f"fp_{co}_1"
    await db.financial_periods.insert_one({"_id": p1, "workspace_id": WS, "company_id": co, "financial_year_id": f"fy_{co}",
                                           "period_code": "2026-01", "label": "2026-01", "start_date": "2026-01-01",
                                           "end_date": "2026-01-31", "period_type": "month", "sequence": 1, "status": "open"})
    await tax_engine.ensure_default_tax_codes(db, WS, co, "CH")
    return p1


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    cols = ("companies", "financial_years", "financial_periods", "journal_entries", "journal_entry_lines",
            "sales_customers", "sales_invoices", "sales_payments", "sales_credit_notes", "sales_tax_codes",
            "sales_gl_mapping", "sales_sequences", "sales_customer_credits", "sales_reminders", "source_documents")
    for c in cols:
        await db[c].delete_many({"workspace_id": WS})
    legacy = ["acct_bv", "qc9434_journal"]
    legacy_before = {c: await db[c].count_documents({}) for c in legacy}

    maker = {"id": "u_mk", "email": "mk@a3"}
    checker = {"id": "u_ck", "email": "ck@a3"}
    CO = "co_a3docs"
    P1 = await _seed(db, CO)

    print("== Référentiel client enrichi (Section 2) ==")
    cust = await ar.create_customer(db, WS, CO, maker, {
        "name": "Client SA", "code": "C-001", "billing_email": "billing@client.test", "phone": "+41 22 000",
        "billing_address": "Av. Test 5", "shipping_address": "Dépôt 9", "jurisdiction": "CH", "language": "fr",
        "payment_terms": "Net 30", "credit_limit": 25000, "tax_ids": {"TVA": "CHE-999"},
        "internal_notes": "VIP", "default_currency": "CHF", "default_tax_code": "VAT_STD"})
    ok("client : tous les champs enrichis persistés",
       cust["billing_email"] == "billing@client.test" and cust["shipping_address"] == "Dépôt 9"
       and cust["credit_limit"] == 25000 and cust["payment_terms"] == "Net 30"
       and cust["tax_ids"].get("TVA") == "CHE-999" and cust["language"] == "fr")
    cust = await ar.update_customer(db, WS, CO, checker, cust["id"], {"phone": "+41 22 111", "credit_limit": 30000})
    ok("client : mise à jour partielle + audit", cust["phone"] == "+41 22 111" and cust["credit_limit"] == 30000
       and len(cust["audit"]) >= 2)

    print("== PDF figé généré à l'approbation (immutable + hash + version) ==")
    inv = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1, "issue_date": "2026-01-05",
        "due_date": "2026-01-06", "lines": [{"description": "Conseil", "qty": 2, "unit_price": 500, "tax_code": "VAT_STD"}]})
    inv = await ar.submit_invoice(db, WS, CO, maker, inv["id"])
    before = await db.source_documents.count_documents({"workspace_id": WS, "company_id": CO, "source_id": inv["id"]})
    ok("aucun document avant approbation", before == 0)
    inv = await ar.approve_invoice(db, WS, CO, checker, inv["id"])
    ok("facture approuvée porte doc + version + sha256",
       inv["source_document_id"] and inv["source_document_version"] == 1 and len(inv["source_document_sha256"]) == 64)
    doc_list = await docs.list_documents(db, WS, CO, source_type="ar_invoice", source_id=inv["id"])
    ok("1 document source figé", len(doc_list) == 1 and doc_list[0]["kind"] == "invoice")
    data, mime, fname = await docs.download_document(db, WS, CO, inv["source_document_id"])
    ok("téléchargement : PDF valide + hash vérifié + mime", data[:5] == b"%PDF-" and mime == "application/pdf" and fname.endswith(".pdf"))

    print("== Immutabilité : ré-approbation = NOUVELLE version, jamais d'écrasement ==")
    # simulate an explicit re-generation by calling store_document again (new version)
    from core.accounting import ar_pdf
    company = await db.companies.find_one({"_id": CO})
    cust_doc = await db.sales_customers.find_one({"_id": cust["id"]})
    inv_doc = await db.sales_invoices.find_one({"_id": inv["id"]})
    pdf2 = ar_pdf.build_invoice_pdf(company=company, customer=cust_doc, invoice={**inv_doc, "id": inv["id"]})
    v2 = await docs.store_document(db, WS, CO, checker, source_type="ar_invoice", source_id=inv["id"], data=pdf2,
                                   filename="facture_v2.pdf", kind="invoice")
    ok("nouvelle version = 2, id distinct", v2["version"] == 2 and v2["id"] != inv["source_document_id"])
    all_docs = await docs.list_documents(db, WS, CO, source_type="ar_invoice", source_id=inv["id"])
    ok("chaîne de versions conservée (2)", len(all_docs) == 2)

    print("== Traçabilité bidirectionnelle Facture <-> PDF <-> Journal ==")
    inv = await ar.post_invoice(db, WS, CO, checker, inv["id"])
    je = await db.journal_entries.find_one({"_id": inv["journal_entry_id"]})
    ok("écriture porte source_document_id (facture -> journal)", je.get("source_document_id") == inv["source_document_id"])
    linked = await db.source_documents.find_one({"_id": inv["source_document_id"]})
    ok("document gelé + lié au journal", linked.get("frozen") is True and linked.get("journal_entry_id") == inv["journal_entry_id"])
    src = await ar.resolve_journal_source(db, WS, CO, inv["journal_entry_id"])
    ok("journal -> source AR -> facture -> PDF",
       src["source_document_id"] == inv["source_document_id"] and src["invoice"] and src["invoice"]["id"] == inv["id"])

    print("== Isolation cross-workspace du document (pas de fuite) ==")
    leaked = await db.source_documents.find_one({"_id": inv["source_document_id"], "workspace_id": "ws_other"})
    ok("document invisible pour un autre workspace", leaked is None)
    try:
        await docs.download_document(db, "ws_other", CO, inv["source_document_id"])
        ok("download cross-workspace refusé", False)
    except Exception as e:
        ok("download cross-workspace -> 404", getattr(e, "status_code", None) == 404)

    print("== Relances / Dunning (facture échue) ==")
    overdue = await dunning.overdue_invoices(db, WS, CO, as_of="2026-06-01")
    ok("facture détectée comme échue", any(o["invoice_id"] == inv["id"] for o in overdue))
    rem = await dunning.create_reminder(db, WS, CO, checker, {"invoice_id": inv["id"], "message": "Merci de régler."})
    ok("relance : niveau 1, PDF stocké, historique",
       rem["level"] == 1 and rem["document_id"] and rem["status"] in ("sent", "failed", "generated"))
    hist = await dunning.list_reminders(db, WS, CO, invoice_id=inv["id"])
    ok("historique des relances (1)", len(hist) == 1 and hist[0]["id"] == rem["id"])
    rdoc = await docs.list_documents(db, WS, CO, source_type="ar_reminder", source_id=inv["id"])
    ok("PDF de relance stocké comme document source", len(rdoc) == 1 and rdoc[0]["kind"] == "reminder")

    print("== Aperçu AR ==")
    ov = await ar.overview(db, WS, CO, as_of="2026-06-01")
    ok("overview : créances/échu/compteurs cohérents",
       ov["open_ar_functional"] > 0 and ov["overdue_functional"] > 0 and ov["customer_count"] == 1)

    print("== Isolation legacy ==")
    legacy_after = {c: await db[c].count_documents({}) for c in legacy}
    ok("aucune collection legacy modifiée", legacy_before == legacy_after)

    for c in cols:
        await db[c].delete_many({"workspace_id": WS})
    print(f"\n{'ALL PASS' if not _fail else 'FAILURES: ' + ', '.join(_fail)}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
