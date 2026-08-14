"""Phase 1.1 — Introduce the workspace tenant root.

The migration is deliberately non-destructive:
- dry-run by default;
- creates at most one workspace for the current legacy installation;
- attaches existing users and companies to that workspace;
- preserves all legacy fields, including ``legacy_prefix``;
- does not touch acct_*, qc9434_*, payroll, reporting, invoices, or ledger data;
- idempotent after a successful commit.

Because the legacy database does not contain reliable metadata for the buying
organization, first-time creation requires explicit workspace identity values.
This prevents the migration from inventing legal/tenant information.

Usage (from backend/):
    python scripts/migrate_phase1_workspace.py \
        --name "Fiduciaire ABC SA" \
        --organization-type fiduciary \
        --jurisdiction CH

    python scripts/migrate_phase1_workspace.py \
        --name "Fiduciaire ABC SA" \
        --organization-type fiduciary \
        --jurisdiction CH \
        --commit

Optional:
    --admin-email admin@example.com

Environment:
    MONGO_URL, DB_NAME and (if --admin-email is omitted) ADMIN_EMAIL.
"""
from __future__ import annotations

import argparse
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

ORG_TYPES = ("company", "group", "fiduciary")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Meelora V2 Phase 1.1 workspace migration")
    parser.add_argument("--commit", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument("--name", help="Workspace / buying organization name")
    parser.add_argument("--organization-type", choices=ORG_TYPES, help="company, group, or fiduciary")
    parser.add_argument("--jurisdiction", help="Primary workspace jurisdiction, e.g. CH or CA")
    parser.add_argument("--admin-email", help="Primary admin email; defaults to ADMIN_EMAIL")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement requise absente: {name}")
    return value


def workspace_id() -> str:
    return f"ws_{uuid.uuid4().hex}"


async def resolve_primary_admin(db, email: str) -> dict:
    admin = await db.users.find_one({"email": email.lower()})
    if not admin:
        raise RuntimeError(f"Administrateur principal introuvable: {email}")
    if admin.get("role") != "admin":
        raise RuntimeError(f"L'utilisateur {email} existe mais n'est pas administrateur")
    return admin


async def inspect_existing_state(db) -> dict:
    workspaces = await db.workspaces.find({}).to_list(20)
    users_total = await db.users.count_documents({})
    users_without = await db.users.count_documents({"workspace_id": {"$exists": False}})
    companies_total = await db.companies.count_documents({})
    companies_without = await db.companies.count_documents({"workspace_id": {"$exists": False}})
    return {
        "workspaces": workspaces,
        "users_total": users_total,
        "users_without": users_without,
        "companies_total": companies_total,
        "companies_without": companies_without,
    }


async def main() -> int:
    args = parse_args()
    mongo_url = require_env("MONGO_URL")
    db_name = require_env("DB_NAME")
    admin_email = (args.admin_email or os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if not admin_email:
        raise RuntimeError("Fournir --admin-email ou définir ADMIN_EMAIL")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"[{mode}] Mongo: {db_name}\n")

    try:
        state = await inspect_existing_state(db)
        workspaces = state["workspaces"]

        if len(workspaces) > 1:
            raise RuntimeError(
                "Plus d'un workspace existe déjà. Cette migration P1.1 cible uniquement "
                "l'installation legacy mono-workspace et refuse de deviner une fusion."
            )

        if workspaces:
            workspace = workspaces[0]
            ws_id = str(workspace["_id"])
            print(f"= workspace existant: {workspace.get('name', '')} ({ws_id})")
            if args.name and args.name != workspace.get("name"):
                print("! --name ignoré: le workspace existe déjà")
            if args.organization_type and args.organization_type != workspace.get("organization_type"):
                print("! --organization-type ignoré: le workspace existe déjà")
            if args.jurisdiction and args.jurisdiction != workspace.get("jurisdiction"):
                print("! --jurisdiction ignoré: le workspace existe déjà")
        else:
            missing = [
                flag for flag, value in (
                    ("--name", args.name),
                    ("--organization-type", args.organization_type),
                    ("--jurisdiction", args.jurisdiction),
                ) if not value
            ]
            if missing:
                raise RuntimeError(
                    "Premier lancement: métadonnées workspace requises: " + ", ".join(missing)
                )
            admin = await resolve_primary_admin(db, admin_email)
            ws_id = workspace_id()
            workspace = {
                "_id": ws_id,
                "name": args.name.strip(),
                "organization_type": args.organization_type,
                "jurisdiction": args.jurisdiction.strip().upper(),
                "primary_admin_user_id": str(admin["_id"]),
                "status": "active",
                "onboarding_completed": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "migration_script",
            }
            print(f"+ créer workspace: {workspace['name']} ({ws_id})")
            print(f"  type={workspace['organization_type']} jurisdiction={workspace['jurisdiction']}")
            print(f"  admin={admin_email} ({workspace['primary_admin_user_id']})")
            if args.commit:
                await db.workspaces.insert_one(workspace)

        print("\n== Users ==")
        print(f"total={state['users_total']} sans workspace_id={state['users_without']}")
        if args.commit and state["users_without"]:
            result = await db.users.update_many(
                {"workspace_id": {"$exists": False}},
                {"$set": {"workspace_id": ws_id, "status": "active"}},
            )
            print(f"+ utilisateurs rattachés: {result.modified_count}")
        elif not args.commit and state["users_without"]:
            print(f"+ rattacherait {state['users_without']} utilisateur(s) à {ws_id}")

        print("\n== Companies ==")
        print(f"total={state['companies_total']} sans workspace_id={state['companies_without']}")
        if args.commit and state["companies_without"]:
            result = await db.companies.update_many(
                {"workspace_id": {"$exists": False}},
                {"$set": {"workspace_id": ws_id, "status": "active"}},
            )
            print(f"+ sociétés rattachées: {result.modified_count}")
        elif not args.commit and state["companies_without"]:
            print(f"+ rattacherait {state['companies_without']} société(s) à {ws_id}")

        if args.commit:
            # Helpful, non-unique indexes only. Uniqueness policy is introduced in P1.3.
            await db.users.create_index("workspace_id")
            await db.companies.create_index("workspace_id")
            await db.workspaces.create_index("organization_type")

            users_orphans = await db.users.count_documents({"workspace_id": {"$exists": False}})
            companies_orphans = await db.companies.count_documents({"workspace_id": {"$exists": False}})
            ws_count = await db.workspaces.count_documents({})
            print("\n== Validation post-commit ==")
            print(f"workspaces={ws_count}")
            print(f"users sans workspace_id={users_orphans}")
            print(f"companies sans workspace_id={companies_orphans}")
            if ws_count != 1 or users_orphans or companies_orphans:
                raise RuntimeError("Validation post-commit échouée")
            print("OK — P1.1 migration validée")
        else:
            print("\nDry-run terminé — aucune écriture effectuée.")
            print("Relancer avec les mêmes paramètres + --commit après validation.")

        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(2)
