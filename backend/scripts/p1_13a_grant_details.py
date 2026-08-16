"""Détaille les grants du dry-run P1.13A corrigé : la dérivation repose sur une
PREUVE d'accès métier legacy réel (P1.10 `company_access`) + module réellement
utilisé par la société, JAMAIS sur un `company_membership` seul, et JAMAIS via un
`platform_role`. Lecture seule (aucune écriture)."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.migrate_p1_13a_access import _company_used_modules, _find_user


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    company_cache, used_cache, user_cache = {}, {}, {}
    rows, excluded = [], []
    checks = {"budgets_implicit": 0, "cross_workspace": 0, "via_platform_role": 0, "via_membership_only": 0}

    meelora = await db.companies.find_one({"legacy_prefix": "acct"})
    meelora_ws = meelora.get("workspace_id") if meelora else None

    async for a in db.company_access.find({}):
        cid, wsid, uid = a.get("company_id"), a.get("workspace_id"), a.get("user_id")
        legacy_role = a.get("access_role") or a.get("role")
        if uid not in user_cache:
            user_cache[uid] = await _find_user(db, uid) or {}
        u = user_cache[uid]
        email = u.get("email", uid)
        platform_role = u.get("platform_role")
        if cid not in company_cache:
            company_cache[cid] = await db.companies.find_one({"id": cid}) or {}
        company = company_cache[cid]
        cname = company.get("name") if company else "?"
        # Platform/support staff: never an automatic business module.
        if platform_role:
            excluded.append((email, cname, f"platform_role='{platform_role}' → aucun module métier automatique (none)"))
            continue
        if not company:
            excluded.append((email, cid, "société introuvable → none"))
            continue
        if cid not in used_cache:
            used_cache[cid] = await _company_used_modules(db, company)
        used = used_cache[cid]
        if not used:
            excluded.append((email, cname, "société n'utilise aucun module (aucune donnée opérationnelle) → none"))
            continue
        for code in sorted(used):
            existing = await db.user_module_access.find_one(
                {"workspace_id": wsid, "company_id": cid, "user_id": uid, "module_code": code})
            if existing:
                continue
            rows.append({"user_id": uid, "email": email, "platform_role": platform_role,
                         "company": cname, "company_id": cid, "legacy_role": legacy_role,
                         "module": code, "level": "read", "workspace_id": wsid})
            if code == "BUDGETS":
                checks["budgets_implicit"] += 1
            if wsid != meelora_ws:
                checks["cross_workspace"] += 1

    print("=== GRANTS DÉTAILLÉS (dry-run P1.13A corrigé) ===")
    print("Règle : PREUVE legacy = P1.10 `company_access` + module réellement utilisé. "
          "Membership seul = jamais. platform_role = jamais auto.\n")
    for i, r in enumerate(rows, 1):
        print(f"[{i}] user_id={r['user_id']}")
        print(f"    email               : {r['email']}")
        print(f"    société             : {r['company']} (id={r['company_id']})")
        print(f"    workspace           : {r['workspace_id']}")
        print(f"    preuve legacy (P1.10): company_access access_role='{r['legacy_role']}' sur cette société")
        print(f"    platform_role       : {r['platform_role']}")
        print(f"    module proposé      : {r['module']}")
        print(f"    niveau proposé      : {r['level']}")
        print(f"    justification       : accès métier legacy RÉEL (P1.10 company_access) sur '{r['company']}' "
              f"QUI UTILISE {r['module']} (données présentes). Dérivation conservatrice = read "
              f"(equal-or-less). Pas dérivé d'un membership ni d'un platform_role.")
        print()

    print("=== EXCLUS (aucun grant — 'none') ===")
    for email, comp, why in excluded:
        print(f"  - {email} @ {comp} : {why}")
    print()

    print("=== INVARIANTS ===")
    print(f"grants totaux                          : {len(rows)}")
    print(f"niveau proposé 'manage' (auto)         : {sum(1 for r in rows if r['level']=='manage')}  (attendu 0)")
    print(f"permissions sensibles auto             : 0  (le script n'écrit JAMAIS dans user_permission_grants)")
    print(f"grants via platform_role               : 0  (tout compte platform_role est exclu → none)")
    print(f"grants par membership seul             : 0  (dérivation basée sur company_access legacy, pas les memberships)")
    print(f"cross-workspace                        : {checks['cross_workspace']}  (attendu 0)")
    print(f"module BUDGETS implicite (5e module)   : {checks['budgets_implicit']}  (attendu 0)")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
