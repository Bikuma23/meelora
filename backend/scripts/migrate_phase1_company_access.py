"""Phase 1.3 — Prepare company_access and permission indexes.

This migration is intentionally conservative. The legacy database does not
contain reliable principal/collaborator assignments, so P1.3 MUST NOT invent
responsibility relationships.

Default behavior:
- dry-run only;
- validates workspace migration integrity;
- creates no company_access rows;
- reports which standard users still need assignments before P1.4 scoping;
- on --commit, creates indexes only.

Optional compatibility seeding:
    --preserve-legacy-access

When explicitly requested, each active non-admin user receives *collaborator*
access to every active company in the same workspace. This preserves the old
"all companies visible" behavior during transition, but it is intentionally
opt-in because it grants broad access. It never creates a principal assignment.
Admins do not need company_access rows because their workspace-scoped admin
role is the authorization override.

Usage (from backend/):
    python scripts/migrate_phase1_company_access.py
    python scripts/migrate_phase1_company_access.py --commit
    python scripts/migrate_phase1_company_access.py --preserve-legacy-access
    python scripts/migrate_phase1_company_access.py --preserve-legacy-access --commit
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Meelora V2 Phase 1.3 company_access migration")
    parser.add_argument("--commit", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument(
        "--preserve-legacy-access",
        action="store_true",
        help="Explicitly seed every active non-admin as collaborator on all active companies in their workspace.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement requise absente: {name}")
    return value


def access_id() -> str:
    return f"cacc_{uuid.uuid4().hex}"


async def validate_foundation(db) -> tuple[list[dict], list[dict], list[dict]]:
    workspaces = await db.workspaces.find({"status": {"$ne": "inactive"}}).to_list(None)
    if not workspaces:
        raise RuntimeError("Aucun workspace actif. Exécuter P1.1 d'abord.")

    users = await db.users.find({"status": {"$ne": "inactive"}}).to_list(None)
    companies = await db.companies.find({"active": {"$ne": False}, "status": {"$ne": "inactive"}}).to_list(None)

    missing_users = [str(u.get("_id")) for u in users if not u.get("workspace_id")]
    missing_companies = [c.get("id", str(c.get("_id"))) for c in companies if not c.get("workspace_id")]
    if missing_users or missing_companies:
        raise RuntimeError(
            "P1.1 incomplète: documents sans workspace_id. "
            f"users={len(missing_users)} companies={len(missing_companies)}"
        )

    ws_ids = {str(w["_id"]) for w in workspaces}
    bad_users = [str(u.get("_id")) for u in users if u.get("workspace_id") not in ws_ids]
    bad_companies = [c.get("id", str(c.get("_id"))) for c in companies if c.get("workspace_id") not in ws_ids]
    if bad_users or bad_companies:
        raise RuntimeError(
            "Références workspace invalides détectées. "
            f"users={len(bad_users)} companies={len(bad_companies)}"
        )
    return workspaces, users, companies


async def planned_accesses(db, users: list[dict], companies: list[dict], preserve: bool) -> list[dict]:
    if not preserve:
        return []
    companies_by_ws: dict[str, list[dict]] = {}
    for company in companies:
        companies_by_ws.setdefault(company["workspace_id"], []).append(company)

    planned = []
    for user in users:
        if user.get("role") == "admin":
            continue
        uid = str(user["_id"])
        for company in companies_by_ws.get(user["workspace_id"], []):
            cid = company.get("id")
            if not cid:
                continue
            existing = await db.company_access.find_one({
                "workspace_id": user["workspace_id"],
                "company_id": cid,
                "user_id": uid,
            })
            if existing:
                continue
            planned.append({
                "_id": access_id(),
                "workspace_id": user["workspace_id"],
                "company_id": cid,
                "user_id": uid,
                "access_role": "collaborator",
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "migration_script",
                "migration_source": "legacy_preserve_access",
            })
    return planned


async def create_indexes(db) -> None:
    await db.company_access.create_index(
        [("workspace_id", 1), ("company_id", 1), ("user_id", 1)],
        unique=True,
        name="uniq_company_access_user",
    )
    await db.company_access.create_index(
        [("workspace_id", 1), ("user_id", 1), ("active", 1)],
        name="idx_company_access_user_active",
    )
    await db.company_access.create_index(
        [("workspace_id", 1), ("company_id", 1), ("access_role", 1)],
        unique=True,
        partialFilterExpression={"active": True, "access_role": "principal"},
        name="uniq_active_principal_per_company",
    )


async def main() -> int:
    args = parse_args()
    client = AsyncIOMotorClient(require_env("MONGO_URL"))
    db = client[require_env("DB_NAME")]
    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"[{mode}] company_access P1.3\n")
    try:
        workspaces, users, companies = await validate_foundation(db)
        print(f"workspaces actifs: {len(workspaces)}")
        print(f"utilisateurs actifs: {len(users)}")
        print(f"sociétés actives: {len(companies)}")

        current = await db.company_access.count_documents({})
        print(f"company_access existants: {current}")

        standard_users = [u for u in users if u.get("role") != "admin"]
        if not args.preserve_legacy_access:
            print("\nAucun accès n'est inféré depuis le legacy.")
            print(f"Utilisateurs standards à attribuer avant P1.4: {len(standard_users)}")
            print("Utiliser --preserve-legacy-access seulement si vous voulez conserver explicitement la visibilité legacy globale.")

        planned = await planned_accesses(db, users, companies, args.preserve_legacy_access)
        if args.preserve_legacy_access:
            print(f"\nAccès collaborateur à créer pour préserver le legacy: {len(planned)}")
            for doc in planned[:20]:
                print(f"  + user={doc['user_id']} company={doc['company_id']} role=collaborator")
            if len(planned) > 20:
                print(f"  ... +{len(planned) - 20} autre(s)")

        if args.commit:
            if planned:
                await db.company_access.insert_many(planned, ordered=False)
            await create_indexes(db)
            duplicates = await db.company_access.aggregate([
                {"$group": {
                    "_id": {"w": "$workspace_id", "c": "$company_id", "u": "$user_id"},
                    "n": {"$sum": 1},
                }},
                {"$match": {"n": {"$gt": 1}}},
            ]).to_list(None)
            principals = await db.company_access.aggregate([
                {"$match": {"active": True, "access_role": "principal"}},
                {"$group": {
                    "_id": {"w": "$workspace_id", "c": "$company_id"},
                    "n": {"$sum": 1},
                }},
                {"$match": {"n": {"$gt": 1}}},
            ]).to_list(None)
            if duplicates or principals:
                raise RuntimeError("Validation company_access échouée après commit")
            print("\nOK — collection/indexes P1.3 validés")
            if not args.preserve_legacy_access and standard_users:
                print("ATTENTION: aucun accès standard n'a été créé. Configurer les attributions avant d'activer le scoping P1.4.")
        else:
            print("\nDry-run terminé — aucune écriture effectuée.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(2)
