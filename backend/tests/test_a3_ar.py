"""ACCOUNTING A3 — Accounts Receivable engine tests (aligned on Financial Core P2).

Covers: tax engine (GST+QST snapshot, versioned CH VAT), invoice lifecycle +
maker-checker + sensitive gates (at service level), canonical GL posting (Dr AR /
Cr Revenue / Cr Tax), idempotent posting, multi-currency (CAD↔USD, CHF↔EUR) with
realised FX gain/loss on payment, full VOID vs partial CREDIT NOTE (distinct),
over-credit guard, available customer credit, aging, and legacy isolation.

Exit 0 = all pass. Throwaway workspace/company; no legacy touched.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.accounting import ar
from core.financial import tax_engine, fx as fx_service

WS = "ws_a3_test"
FY = "fy_a3_test"
_fail = []


def ok(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _fail.append(name)


async def expect_http(name, coro, code):
    try:
        await coro
        ok(f"{name} (attendu HTTP {code})", False)
    except HTTPException as e:
        ok(f"{name} -> {e.status_code}", e.status_code == code)


async def _seed_company(db, co, currency, jurisdiction):
    await db.companies.insert_one({"_id": co, "workspace_id": WS, "functional_currency": currency, "jurisdiction": jurisdiction})
    await db.financial_years.insert_one({"_id": f"{FY}_{co}", "workspace_id": WS, "company_id": co,
                                         "label": "2026", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"})
    p1 = f"fp_{co}_1"
    await db.financial_periods.insert_one({"_id": p1, "workspace_id": WS, "company_id": co, "financial_year_id": f"{FY}_{co}",
                                           "period_code": "2026-01", "label": "2026-01", "start_date": "2026-01-01",
                                           "end_date": "2026-01-31", "period_type": "month", "sequence": 1, "status": "open"})
    p2 = f"fp_{co}_2"
    await db.financial_periods.insert_one({"_id": p2, "workspace_id": WS, "company_id": co, "financial_year_id": f"{FY}_{co}",
                                           "period_code": "2026-02", "label": "2026-02", "start_date": "2026-02-01",
                                           "end_date": "2026-02-28", "period_type": "month", "sequence": 2, "status": "open"})
    await tax_engine.ensure_default_tax_codes(db, WS, co, jurisdiction)
    return p1, p2


async def _je_lines(db, je_id):
    return await db.journal_entry_lines.find({"journal_entry_id": je_id}).to_list(None)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    cols = ("companies", "financial_years", "financial_periods", "journal_entries", "journal_entry_lines",
            "sales_customers", "sales_invoices", "sales_payments", "sales_credit_notes", "sales_tax_codes",
            "sales_gl_mapping", "sales_sequences", "sales_customer_credits", "exchange_rates")
    for c in cols:
        await db[c].delete_many({"workspace_id": WS})

    legacy_cols = ["acct_bv", "acct_periods", "acct_ledger", "qc9434_journal", "qc9434_clients", "qc9434_periods"]
    legacy_before = {c: await db[c].count_documents({}) for c in legacy_cols}

    maker = {"id": "u_maker", "email": "maker@a3"}
    checker = {"id": "u_checker", "email": "checker@a3"}

    # ================= QC company (CAD functional) =================
    CO = "co_a3_qc"
    P1, P2 = await _seed_company(db, CO, "CAD", "CA-QC")

    print("== Moteur fiscal : GST 5% + QST 9,975% (snapshot) ==")
    codes = {t["code"] for t in await tax_engine.list_tax_codes(db, WS, CO)}
    ok("codes QC seedés (GST_QST, GST, ZERO, EXEMPT)", {"GST_QST", "GST", "ZERO", "EXEMPT"} <= codes)
    tc = await tax_engine.get_tax_code(db, WS, CO, "GST_QST")
    snap = tax_engine.compute_line_tax(tc, 100.0, "2026-01-15")
    ok("GST_QST sur 100 = 14.98 (5 + 9.975)", snap["tax_total"] == 14.98 and len(snap["components"]) == 2)

    print("== Facture CAD : cycle + maker-checker + posting GL canonique ==")
    cust = await ar.create_customer(db, WS, CO, maker, {"name": "Client QC", "default_currency": "CAD", "default_tax_code": "GST_QST"})
    inv = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1, "issue_date": "2026-01-15",
        "lines": [{"description": "Service", "qty": 1, "unit_price": 100, "revenue_account_code": "REVENUE", "tax_code": "GST_QST"}]})
    ok("facture brouillon équilibrée (subtotal 100, tax 14.98, total 114.98)",
       inv["subtotal"] == 100 and inv["tax_total"] == 14.98 and inv["total"] == 114.98 and inv["status"] == "draft")
    inv = await ar.submit_invoice(db, WS, CO, maker, inv["id"])
    await expect_http("maker ne peut pas approuver sa facture", ar.approve_invoice(db, WS, CO, maker, inv["id"]), 403)
    inv = await ar.approve_invoice(db, WS, CO, checker, inv["id"])
    ok("approuvée par un autre utilisateur", inv["status"] == "approved")
    je_before = await db.journal_entries.count_documents({"workspace_id": WS, "company_id": CO, "external_id": inv["id"]})
    ok("aucune écriture avant POST", je_before == 0)
    inv = await ar.post_invoice(db, WS, CO, checker, inv["id"])
    ok("facture posted + numéro + journal_entry_id", inv["status"] == "posted" and inv["number"] and inv["journal_entry_id"])
    jes = await db.journal_entries.find({"workspace_id": WS, "company_id": CO, "external_id": inv["id"]}).to_list(None)
    ok("exactement 1 écriture canonique", len(jes) == 1)
    lines = await _je_lines(db, jes[0]["_id"])
    ar_line = [l for l in lines if l["account_code"] == "AR"][0]
    rev = sum(l["credit"] for l in lines if l["account_code"] == "REVENUE")
    tax = sum(l["credit"] for l in lines if l["account_code"] in ("TAX_GST_PAYABLE", "TAX_QST_PAYABLE"))
    ok("Dr AR 114.98 / Cr Produits 100 / Cr Taxes 14.98", ar_line["debit"] == 114.98 and rev == 100 and tax == 14.98)
    ok("écriture équilibrée", round(sum(l["debit"] for l in lines), 2) == round(sum(l["credit"] for l in lines), 2))
    ok("source_system=sales, tie période canonique", jes[0]["source_system"] == "sales" and jes[0]["financial_period_id"] == P1)
    # idempotence
    inv2 = await ar.post_invoice(db, WS, CO, checker, inv["id"])
    dup = await db.journal_entries.count_documents({"workspace_id": WS, "company_id": CO, "external_id": inv["id"]})
    ok("POST idempotent (pas de doublon)", dup == 1 and inv2["journal_entry_id"] == inv["journal_entry_id"])

    print("== Encaissement CAD (même devise, pas de FX) ==")
    pay = await ar.create_payment(db, WS, CO, checker, {"invoice_id": inv["id"], "amount": 114.98, "date": "2026-01-20"})
    ok("encaissement sans FX (diff 0)", pay["realized_fx"] == 0.0)
    inv_paid = await ar.get_invoice(db, WS, CO, inv["id"])
    ok("facture payée (balance 0, status paid)", inv_paid["balance"] == 0.0 and inv_paid["status"] == "paid")

    print("== Note de crédit PARTIELLE (réutilise snapshot fiscal original) ==")
    inv3 = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1, "issue_date": "2026-01-16",
        "lines": [{"unit_price": 200, "tax_code": "GST_QST", "revenue_account_code": "REVENUE"}]})
    inv3 = await ar.submit_invoice(db, WS, CO, maker, inv3["id"])
    inv3 = await ar.approve_invoice(db, WS, CO, checker, inv3["id"])
    inv3 = await ar.post_invoice(db, WS, CO, checker, inv3["id"])
    await expect_http("sur-crédit interdit (>200)", ar.create_credit_note(db, WS, CO, maker, {
        "invoice_id": inv3["id"], "lines": [{"invoice_line_index": 0, "net_credit": 250}]}), 422)
    cn = await ar.create_credit_note(db, WS, CO, maker, {"invoice_id": inv3["id"],
        "lines": [{"invoice_line_index": 0, "net_credit": 50}]})
    ok("note de crédit : 50 + taxe proportionnelle 7.49 = 57.49", cn["subtotal"] == 50 and cn["tax_total"] == 7.49 and cn["total"] == 57.49)
    cn = await ar.submit_credit_note(db, WS, CO, maker, cn["id"])
    await expect_http("maker ne peut pas approuver sa note de crédit", ar.approve_credit_note(db, WS, CO, maker, cn["id"]), 403)
    cn = await ar.approve_credit_note(db, WS, CO, checker, cn["id"])
    cn = await ar.post_credit_note(db, WS, CO, checker, cn["id"])
    ok("note de crédit posted + numéro + JE", cn["status"] == "posted" and cn["number"] and cn["journal_entry_id"])
    cn_lines = await _je_lines(db, cn["journal_entry_id"])
    cn_ar = [l for l in cn_lines if l["account_code"] == "AR"][0]
    ok("note de crédit : Cr AR 57.49 (réduction)", cn_ar["credit"] == 57.49)
    inv3_after = await ar.get_invoice(db, WS, CO, inv3["id"])
    ok("facture : credited_total 57.49, balance réduite", inv3_after["credited_total"] == 57.49 and inv3_after["balance"] == 172.46)

    print("== Extourne COMPLÈTE (VOID) d'une facture non payée + concepts distincts ==")
    inv4 = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1,
        "lines": [{"unit_price": 80, "tax_code": "GST", "revenue_account_code": "REVENUE"}]})
    inv4 = await ar.submit_invoice(db, WS, CO, maker, inv4["id"])
    inv4 = await ar.approve_invoice(db, WS, CO, checker, inv4["id"])
    inv4 = await ar.post_invoice(db, WS, CO, checker, inv4["id"])
    orig_je = inv4["journal_entry_id"]
    voided = await ar.void_invoice(db, WS, CO, checker, inv4["id"])
    ok("facture void + JE d'extourne lié", voided["status"] == "void" and voided["reversal_journal_entry_id"])
    orig = await db.journal_entries.find_one({"_id": orig_je})
    ok("JE original jamais muté (back-ref ajouté)", orig.get("reversed_by_journal_entry_id") == voided["reversal_journal_entry_id"])
    # VOID interdit après paiement
    await expect_http("VOID interdit si payée (utiliser note de crédit)", ar.void_invoice(db, WS, CO, checker, inv["id"]), 409)

    print("== Période verrouillée/clôturée bloque le posting + séquentiel ==")
    from core.accounting import gl as gl_service
    inv5 = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1,
        "lines": [{"unit_price": 10, "tax_code": "EXEMPT", "revenue_account_code": "REVENUE"}]})
    inv5 = await ar.submit_invoice(db, WS, CO, maker, inv5["id"]); inv5 = await ar.approve_invoice(db, WS, CO, checker, inv5["id"])
    await gl_service.transition_period(db, WS, CO, checker, P1, "locked")
    await expect_http("posting bloqué (période verrouillée)", ar.post_invoice(db, WS, CO, checker, inv5["id"]), 409)
    await gl_service.transition_period(db, WS, CO, checker, P1, "open")
    inv5 = await ar.post_invoice(db, WS, CO, checker, inv5["id"])
    ok("posting ok après déverrouillage", inv5["status"] == "posted")
    # P2 bloqué tant que P1 non clôturée
    inv6 = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P2,
        "lines": [{"unit_price": 10, "tax_code": "EXEMPT", "revenue_account_code": "REVENUE"}]})
    inv6 = await ar.submit_invoice(db, WS, CO, maker, inv6["id"]); inv6 = await ar.approve_invoice(db, WS, CO, checker, inv6["id"])
    await expect_http("P2 bloquée tant que P1 non clôturée", ar.post_invoice(db, WS, CO, checker, inv6["id"]), 409)

    # ================= USD invoice against CAD functional (realised FX) =================
    print("== Multidevise CAD↔USD : facture puis paiement à taux différent -> gain/perte FX ==")
    await fx_service.record_rate(db, WS, CO, from_currency="USD", to_currency="CAD", rate=1.30, rate_date="2026-01-01")
    inv_usd = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1, "currency": "USD",
        "issue_date": "2026-01-10", "lines": [{"unit_price": 1000, "tax_code": "EXEMPT", "revenue_account_code": "REVENUE"}]})
    ok("FX snapshot USD->CAD 1.30 figé", inv_usd["fx"]["rate"] == 1.30 and inv_usd["currency"] == "USD")
    inv_usd = await ar.submit_invoice(db, WS, CO, maker, inv_usd["id"]); inv_usd = await ar.approve_invoice(db, WS, CO, checker, inv_usd["id"])
    inv_usd = await ar.post_invoice(db, WS, CO, checker, inv_usd["id"])
    usd_lines = await _je_lines(db, inv_usd["journal_entry_id"])
    usd_ar = [l for l in usd_lines if l["account_code"] == "AR"][0]
    ok("AR fonctionnel = 1000 USD * 1.30 = 1300 CAD, txn conservée", usd_ar["debit"] == 1300.0 and usd_ar["txn_debit"] == 1000.0)
    # payment at 1.35 -> bank 1350 CAD vs AR 1300 -> FX gain 50
    pay_usd = await ar.create_payment(db, WS, CO, checker, {"invoice_id": inv_usd["id"], "amount": 1000, "date": "2026-01-25", "fx_rate": 1.35})
    ok("gain de change réalisé = 50 CAD", pay_usd["realized_fx"] == 50.0)
    pj = await _je_lines(db, pay_usd["journal_entry_id"])
    bank = [l for l in pj if l["account_code"] == "BANK"][0]
    gain = [l for l in pj if l["account_code"] == "FX_GAIN"]
    ok("Dr Banque 1350 / Cr AR 1300 / Cr Gain FX 50 (équilibré)",
       bank["debit"] == 1350.0 and gain and gain[0]["credit"] == 50.0
       and round(sum(l["debit"] for l in pj), 2) == round(sum(l["credit"] for l in pj), 2))

    # ================= CH company (CHF functional) CHF↔EUR with FX loss =================
    print("== Multidevise CHF↔EUR + TVA CH versionnée + perte FX ==")
    CO2 = "co_a3_ch"
    P1b, _ = await _seed_company(db, CO2, "CHF", "CH")
    tcv = await tax_engine.get_tax_code(db, WS, CO2, "VAT_STD")
    ok("TVA CH versionnée : 8.1% en 2026 (vs 7.7% avant 2024)",
       tax_engine.compute_line_tax(tcv, 100, "2026-01-01")["tax_total"] == 8.1
       and tax_engine.compute_line_tax(tcv, 100, "2023-06-01")["tax_total"] == 7.7)
    await fx_service.record_rate(db, WS, CO2, from_currency="EUR", to_currency="CHF", rate=0.95, rate_date="2026-01-01")
    cust2 = await ar.create_customer(db, WS, CO2, maker, {"name": "Kunde EUR", "default_currency": "EUR"})
    inv_eur = await ar.create_invoice(db, WS, CO2, maker, {"customer_id": cust2["id"], "period_id": P1b, "currency": "EUR",
        "issue_date": "2026-01-05", "lines": [{"unit_price": 500, "tax_code": "EXEMPT", "revenue_account_code": "REVENUE"}]})
    inv_eur = await ar.submit_invoice(db, WS, CO2, maker, inv_eur["id"]); inv_eur = await ar.approve_invoice(db, WS, CO2, checker, inv_eur["id"])
    inv_eur = await ar.post_invoice(db, WS, CO2, checker, inv_eur["id"])
    # payment at 0.90 -> bank 450 CHF vs AR 475 CHF -> FX loss 25
    pay_eur = await ar.create_payment(db, WS, CO2, checker, {"invoice_id": inv_eur["id"], "amount": 500, "date": "2026-01-28", "fx_rate": 0.90})
    ok("perte de change réalisée = -25 CHF", pay_eur["realized_fx"] == -25.0)
    pj2 = await _je_lines(db, pay_eur["journal_entry_id"])
    loss = [l for l in pj2 if l["account_code"] == "FX_LOSS"]
    ok("Dr Perte FX 25 (équilibré)", loss and loss[0]["debit"] == 25.0
       and round(sum(l["debit"] for l in pj2), 2) == round(sum(l["credit"] for l in pj2), 2))

    print("== Note de crédit sur facture PAYÉE -> crédit client disponible ==")
    inv7 = await ar.create_invoice(db, WS, CO, maker, {"customer_id": cust["id"], "period_id": P1,
        "lines": [{"unit_price": 100, "tax_code": "EXEMPT", "revenue_account_code": "REVENUE"}]})
    inv7 = await ar.submit_invoice(db, WS, CO, maker, inv7["id"]); inv7 = await ar.approve_invoice(db, WS, CO, checker, inv7["id"])
    inv7 = await ar.post_invoice(db, WS, CO, checker, inv7["id"])
    await ar.create_payment(db, WS, CO, checker, {"invoice_id": inv7["id"], "amount": 100, "date": "2026-01-22"})
    cn2 = await ar.create_credit_note(db, WS, CO, maker, {"invoice_id": inv7["id"], "lines": [{"invoice_line_index": 0, "net_credit": 40}]})
    cn2 = await ar.submit_credit_note(db, WS, CO, maker, cn2["id"]); cn2 = await ar.approve_credit_note(db, WS, CO, checker, cn2["id"])
    cn2 = await ar.post_credit_note(db, WS, CO, checker, cn2["id"])
    ok("crédit client disponible créé (facture déjà payée)", cn2["creates_customer_credit"] is True)
    cust_after = await ar.get_customer(db, WS, CO, cust["id"])
    ok("solde de crédit client = 40", cust_after.get("credit_balance") == 40.0)

    print("== Aging (devise fonctionnelle) ==")
    ag = await ar.aging(db, WS, CO, as_of="2026-01-31")
    ok("aging renvoie des buckets en CAD", ag["functional_currency"] == "CAD" and isinstance(ag["buckets"], dict))

    print("== Isolation legacy acct_*/qc9434_* ==")
    legacy_after = {c: await db[c].count_documents({}) for c in legacy_cols}
    ok("aucune collection legacy modifiée", legacy_before == legacy_after)

    for c in cols:
        await db[c].delete_many({"workspace_id": WS})
    print(f"\n{'ALL PASS' if not _fail else 'FAILURES: ' + ', '.join(_fail)}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
