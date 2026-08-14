"""Phase 1.5 — Prepare fiduciary mandate indexes.

This migration does not infer mandates from legacy company names or prefixes.
Mandates require an explicit principal owner, so they are created through the
P1.5 API/UI after company_access assignments are known.

Default is dry-run. ``--commit`` creates only the defensive indexes.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


def parse_args():
    parser = argparse.ArgumentParser(description="Meelora V2 Phase 1.5 mandate preparation")
    parser.add_argument("--commit", action="store_true", help="Create indexes. Default is dry-run.")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement requise absente: {name}")
    return value


async def create_indexes(db):
    await db.mandates.create_index(
        [("workspace_id", 1), ("company_id", 1)],
        unique=True,
        partialFilterExpression={"status": "active"},
        name="uniq_active_mandate_per_company",
    )
    await db.mandates.create_index(
        [("workspace_id", 1), ("mandate_code", 1)],
        unique=True,
        partialFilterExpression={"status": "active"},
        name="uniq_active_mandate_code",
    )
    await db.mandates.create_index(
        [("workspace_id", 1), ("principal_user_id", 1), ("status", 1)],
        name="idx_mandates_principal_status",
    )


async def main():
    args = parse_args()
    client = AsyncIOMotorClient(require_env("MONGO_URL"))
    db = client[require_env("DB_NAME")]
    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"[{mode}] mandates P1.5\n")
    try:
        fiduciaries = await db.workspaces.count_documents({"organization_type": "fiduciary", "status": {"$ne": "inactive"}})
        mandates = await db.mandates.count_documents({})
        print(f"workspaces fiduciaires actifs: {fiduciaries}")
        print(f"mandats existants: {mandates}")
        duplicates_company = await db.mandates.aggregate([
            {"$match": {"status": {"$ne": "inactive"}}},
            {"$group": {"_id": {"w": "$workspace_id", "c": "$company_id"}, "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
        ]).to_list(None)
        duplicates_code = await db.mandates.aggregate([
            {"$match": {"status": {"$ne": "inactive"}}},
            {"$group": {"_id": {"w": "$workspace_id", "code": "$mandate_code"}, "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
        ]).to_list(None)
        if duplicates_company or duplicates_code:
            raise RuntimeError("Doublons de mandats actifs détectés; corriger avant création des indexes")
        if args.commit:
            await create_indexes(db)
            print("\nOK — indexes mandates P1.5 créés")
        else:
            print("\nDry-run terminé — aucun mandat inventé, aucune écriture effectuée.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(2)
