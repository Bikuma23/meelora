"""
Étapes 2-3 — Ajouter `company_id` à tous les documents existants des
collections acct_* et qc9434_*, en les rattachant aux 2 compagnies créées
par seed_companies.py.

SANS EFFET sur les routes actuelles : aucune lecture ne filtre encore par
company_id à ce stade (ça, c'est l'étape 4, volontairement séparée et
faite route par route, pas par un script global).

Sécurité :
    - Dry-run par défaut : affiche ce qui serait modifié, n'écrit rien.
    - Idempotent : ne touche jamais un document qui a déjà company_id.
    - Ne touche PAS employees/departments/hypotheses/journal/locks —
      volontairement laissés pour un script séparé une fois le module
      Salaires & Budget migré (hors périmètre de cette étape).

Usage :
    python scripts/seed_companies.py --commit        # d'abord, une seule fois
    python scripts/backfill_company_id.py            # dry-run
    python scripts/backfill_company_id.py --commit   # écrit réellement
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

COMMIT = "--commit" in sys.argv

# Collections issues du module Comptabilité existant (/acct/*) -> legacy_prefix "acct"
ACCT_COLLECTIONS = [
    "acct_account_map", "acct_budget_managers", "acct_bv", "acct_email_last",
    "acct_email_log", "acct_external_contacts", "acct_external_email_log",
    "acct_kpi_adjust", "acct_ledger", "acct_line_comments", "acct_manager_notes",
    "acct_margination", "acct_periods", "acct_settings", "acct_template",
]

# Collections issues du module 9434-3977 QC inc. (/qc9434/*) -> legacy_prefix "qc9434"
QC9434_COLLECTIONS = [
    "qc9434_accounts", "qc9434_bills", "qc9434_clients", "qc9434_entries",
    "qc9434_external_contacts", "qc9434_external_email_log", "qc9434_files",
    "qc9434_invoices", "qc9434_settings", "qc9434_templates", "qc9434_years",
]


async def backfill_group(db, collections, legacy_prefix, company_id):
    total_matched, total_updated = 0, 0
    for coll_name in collections:
        coll = db[coll_name]
        query = {"company_id": {"$exists": False}}
        count = await coll.count_documents(query)
        total_matched += count
        if count == 0:
            continue
        print(f"  {coll_name}: {count} document(s) sans company_id")
        if COMMIT:
            res = await coll.update_many(query, {"$set": {"company_id": company_id}})
            total_updated += res.modified_count
    return total_matched, total_updated


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    print(f"{'[COMMIT]' if COMMIT else '[DRY-RUN]'} Mongo: {os.environ['DB_NAME']}\n")

    companies = await db.companies.find({"legacy_prefix": {"$exists": True}}).to_list(10)
    by_prefix = {c["legacy_prefix"]: c["id"] for c in companies}

    if "acct" not in by_prefix or "qc9434" not in by_prefix:
        print("ERREUR: lancer d'abord seed_companies.py --commit — "
              "les 2 compagnies attendues (legacy_prefix=acct/qc9434) sont introuvables.")
        client.close()
        return

    print("== Module Comptabilité existant (acct_*) ==")
    m1, u1 = await backfill_group(db, ACCT_COLLECTIONS, "acct", by_prefix["acct"])

    print("\n== Module 9434-3977 QC inc. (qc9434_*) ==")
    m2, u2 = await backfill_group(db, QC9434_COLLECTIONS, "qc9434", by_prefix["qc9434"])

    print(f"\nTotal documents concernés : {m1 + m2}")
    if COMMIT:
        print(f"Total documents mis à jour : {u1 + u2}")
    else:
        print("Dry-run terminé — relancer avec --commit pour écrire.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
