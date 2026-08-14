"""
Étape 1 — Créer db.companies et y insérer les 2 mandats existants.

Idempotent : peut être relancé sans dupliquer si les compagnies existent déjà
(matché par `legacy_prefix`, un champ temporaire utilisé seulement pendant
la migration pour faire le lien avec l'ancien schéma).

Usage :
    cd backend
    python scripts/seed_companies.py            # dry-run, n'écrit rien
    python scripts/seed_companies.py --commit   # écrit réellement

Utilise les mêmes variables d'environnement que server.py (.env) :
    MONGO_URL, DB_NAME
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

COMMIT = "--commit" in sys.argv

# Les 2 mandats existants, déduits de l'analyse de server.py.
# ⚠️ Vérifier / compléter "name" avant de lancer en --commit — ce sont des
# valeurs par défaut, pas une donnée officielle tirée de la base.
SEED_COMPANIES = [
    {
        "legacy_prefix": "acct",  # sert à identifier ce doc lors du backfill (étape 2)
        "name": "Meelora",
        "jurisdiction": "CA-QC",
        "currency": "CAD",
        "locale": "fr-CA",
        "fiscal_year_end_month": 12,
        "active": True,
    },
    {
        "legacy_prefix": "qc9434",
        "name": "9434-3977 QC inc.",
        "jurisdiction": "CA-QC",
        "currency": "CAD",
        "locale": "fr-CA",
        "fiscal_year_end_month": 12,
        "active": True,
    },
]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    print(f"{'[COMMIT]' if COMMIT else '[DRY-RUN]'} Mongo: {os.environ['DB_NAME']}\n")

    for spec in SEED_COMPANIES:
        existing = await db.companies.find_one({"legacy_prefix": spec["legacy_prefix"]})
        if existing:
            print(f"  = déjà présent : {spec['name']} (id={existing['id']}) — rien à faire")
            continue

        doc = {
            "id": str(uuid.uuid4()),
            "legacy_prefix": spec["legacy_prefix"],
            "name": spec["name"],
            "jurisdiction": spec["jurisdiction"],
            "currency": spec["currency"],
            "locale": spec["locale"],
            "fiscal_year_end_month": spec["fiscal_year_end_month"],
            "chart_of_accounts_template_id": None,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "migration_script",
        }

        if COMMIT:
            await db.companies.insert_one(doc)
            print(f"  + créé : {spec['name']} -> id={doc['id']}")
        else:
            print(f"  + (dry-run) créerait : {spec['name']} -> id={doc['id']}")

    print("\nTerminé." if COMMIT else "\nDry-run terminé — relancer avec --commit pour écrire.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
