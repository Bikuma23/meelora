"""Sauvegarde préalable P1.13A (lecture seule → écrit uniquement des fichiers de
backup JSON hors DB). Dump des collections d'accès/identité + snapshot des
compteurs financiers pour prouver l'absence de modification financière.

Usage: python scripts/backup_p1_13a.py [--tag before|after]
Sortie: /app/backend/backups/p1_13a_<timestamp>_<tag>/
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

ACCESS_COLLECTIONS = [
    "company_access", "company_memberships", "workspace_memberships",
    "user_module_access", "user_permission_grants", "workspace_module_entitlements",
    "users", "companies",
]
FINANCIAL_COLLECTIONS = [
    "acct_periods", "acct_bv", "acct_ledger", "trial_balance_lines",
    "journal_entries", "journal_entry_lines", "journal", "account_mappings",
    "report_runs", "employees", "departments", "hypotheses",
]


def _default(o):
    try:
        return str(o)
    except Exception:
        return None


async def main(tag: str):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / "backups" / f"p1_13a_{ts}_{tag}"
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "tag": tag,
                "db": os.environ["DB_NAME"], "access_counts": {}, "financial_counts": {}}

    existing = set(await db.list_collection_names())
    for coll in ACCESS_COLLECTIONS:
        if coll not in existing:
            manifest["access_counts"][coll] = 0
            continue
        docs = await db[coll].find({}).to_list(None)
        (outdir / f"{coll}.json").write_text(json.dumps(docs, default=_default, ensure_ascii=False, indent=2))
        manifest["access_counts"][coll] = len(docs)

    for coll in FINANCIAL_COLLECTIONS:
        manifest["financial_counts"][coll] = (await db[coll].count_documents({})) if coll in existing else 0

    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Backup [{tag}] -> {outdir}")
    print("access_counts    :", manifest["access_counts"])
    print("financial_counts :", manifest["financial_counts"])
    client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="before")
    asyncio.run(main(p.parse_args().tag))
