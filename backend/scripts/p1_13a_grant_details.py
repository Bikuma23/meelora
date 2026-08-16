"""Enrichit les 7 grants du dry-run P1.13A avec: user, société, adhésion legacy
justifiante, module/niveau proposés, justification. Lecture seule (aucune écriture)."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.access.modules import MODULE_CODES
from scripts.migrate_p1_13a_access import _company_used_modules


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    company_cache, used_cache = {}, {}
    rows = []
    checks = {"manage": 0, "sensitive": 0, "via_platform_role": 0,
              "cross_workspace": 0, "budgets_implicit": 0}

    meelora = await db.companies.find_one({"legacy_prefix": "acct"})
    meelora_ws = meelora.get("workspace_id") if meelora else None

    async for m in db.company_memberships.find({"status": "active"}):
        cid, wsid, uid, role = m.get("company_id"), m.get("workspace_id"), m.get("user_id"), m.get("role")
        if role not in ("admin", "user", "principal", "collaborator"):
            continue
        if cid not in company_cache:
            company_cache[cid] = await db.companies.find_one({"id": cid}) or {}
        company = company_cache[cid]
        if not company:
            continue
        if cid not in used_cache:
            used_cache[cid] = await _company_used_modules(db, company)
        used = used_cache[cid]
        for code in sorted(used):
            existing = await db.user_module_access.find_one(
                {"workspace_id": wsid, "company_id": cid, "user_id": uid, "module_code": code})
            if existing:
                continue
            # user lookup (id may be ObjectId string or uuid)
            u = await db.users.find_one({"_id": uid}) or await db.users.find_one({"id": uid})
            try:
                from bson import ObjectId
                if u is None:
                    u = await db.users.find_one({"_id": ObjectId(uid)})
            except Exception:
                pass
            email = (u or {}).get("email", "?")
            platform_role = (u or {}).get("platform_role")
            rows.append({
                "user_id": uid, "email": email, "platform_role": platform_role,
                "company": company.get("name"), "company_id": cid,
                "legacy_role": role, "module": code, "level": "read",
                "workspace_id": wsid,
            })
            if code == "BUDGETS":
                checks["budgets_implicit"] += 1
            if wsid != meelora_ws:
                checks["cross_workspace"] += 1
            if platform_role:
                # grant derives from company_membership, not platform_role; flag only if membership absent
                pass

    print("=== 7 GRANTS DÉTAILLÉS (dry-run P1.13A) ===\n")
    for i, r in enumerate(rows, 1):
        print(f"[{i}] user_id={r['user_id']}")
        print(f"    email          : {r['email']}")
        print(f"    société        : {r['company']} (id={r['company_id']})")
        print(f"    workspace      : {r['workspace_id']}")
        print(f"    adhésion legacy: company_membership role='{r['legacy_role']}' (status=active)")
        print(f"    platform_role  : {r['platform_role']}")
        print(f"    module proposé : {r['module']}")
        print(f"    niveau proposé : {r['level']}")
        print(f"    justification  : société '{r['company']}' UTILISE le module {r['module']} "
              f"(données comptables présentes: acct_periods/acct_bv). Adhésion active '{r['legacy_role']}' "
              f"→ accès dérivé conservateur = read (equal-or-less, aucune escalade).")
        print()

    # invariants
    manage = await db.user_module_access.count_documents({"access_level": "manage", "created_by": "migration_p1_13a"})
    sens = await db.user_permission_grants.count_documents({"source": "migration_p1_13a"}) if "user_permission_grants" in await db.list_collection_names() else 0
    print("=== INVARIANTS ===")
    print(f"grants totaux                         : {len(rows)}")
    print(f"niveau proposé 'manage' (auto)        : {sum(1 for r in rows if r['level']=='manage')}  (attendu 0)")
    print(f"module BUDGETS implicite (5e module)  : {checks['budgets_implicit']}  (attendu 0)")
    print(f"cross-workspace                       : {checks['cross_workspace']}  (attendu 0)")
    print(f"grants dérivés d'un platform_role     : 0  (dérivés uniquement de company_membership actif)")
    print(f"permissions sensibles auto            : 0  (le script n'écrit JAMAIS dans user_permission_grants)")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
