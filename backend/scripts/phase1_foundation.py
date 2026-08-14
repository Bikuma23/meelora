"""PHASE 1 — FONDATION (strangler, non destructif).

Crée un workspace par défaut et rattache les données existantes :
  - workspaces (organization_type=company, primary_jurisdiction=CA, jurisdictions=[CH,CA])
  - companies : workspace_id, company_type, industry, jurisdiction
  - users : workspace_id (les rôles NE sont PAS modifiés ; les 'editor' sont seulement rapportés)
  - company_access : admin -> principal sur chaque société
  - journal : workspace_id (stamp)

Usage :
  python scripts/phase1_foundation.py            # DRY RUN (aucune écriture)
  python scripts/phase1_foundation.py --commit   # applique
Idempotent : réexécutable sans effet de bord.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
COMMIT = "--commit" in sys.argv
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    report = {"examined": 0, "changed": 0, "skipped": 0, "warnings": [], "errors": []}
    mode = "COMMIT" if COMMIT else "DRY RUN"
    print(f"=== PHASE 1 FOUNDATION — {mode} ===")

    # 1) Workspace par défaut (réutilise s'il existe)
    ws = await db.workspaces.find_one({})
    if ws:
        ws_id = ws["id"]
        print(f"[=] Workspace existant réutilisé : {ws['name']} ({ws_id})")
        report["skipped"] += 1
    else:
        ws_id = str(uuid.uuid4())
        doc = {"id": ws_id, "name": "Meelora", "organization_type": "company",
               "primary_jurisdiction": "CA", "jurisdictions": ["CH", "CA"],
               "onboarding_complete": True, "created_at": now()}
        print(f"[+] Création workspace par défaut 'Meelora' ({ws_id}) org=company juris=CH,CA")
        if COMMIT:
            await db.workspaces.insert_one(doc)
        report["changed"] += 1

    # 2) Companies
    comps = await db.companies.find({}).to_list(500)
    for c in comps:
        report["examined"] += 1
        upd = {}
        if not c.get("workspace_id"):
            upd["workspace_id"] = ws_id
        if not c.get("company_type"):
            upd["company_type"] = "operating"
        if "industry" not in c:
            upd["industry"] = ""
        if not c.get("jurisdiction"):
            upd["jurisdiction"] = "CA"  # entités québécoises existantes
        if upd:
            print(f"[+] company '{c.get('name')}' <- {upd}")
            if COMMIT:
                await db.companies.update_one({"_id": c["_id"]}, {"$set": upd})
            report["changed"] += 1
        else:
            report["skipped"] += 1

    # 3) Users
    users = await db.users.find({}).to_list(1000)
    admins = []
    for u in users:
        report["examined"] += 1
        if u.get("role") == "editor":
            report["warnings"].append(f"user {u.get('email')} a le rôle legacy 'editor' (à normaliser vers 'user' en phase ultérieure)")
        if u.get("role") == "admin":
            admins.append(u)
        if not u.get("workspace_id"):
            print(f"[+] user '{u.get('email')}' <- workspace_id")
            if COMMIT:
                await db.users.update_one({"_id": u["_id"]}, {"$set": {"workspace_id": ws_id}})
            report["changed"] += 1
        else:
            report["skipped"] += 1

    # 4) company_access : admin -> principal sur chaque société
    if not admins:
        report["warnings"].append("Aucun admin trouvé — company_access principal non créé")
    for c in comps:
        cid = c.get("id")
        if not cid:
            continue
        for a in admins:
            aid = str(a["_id"])
            exists = await db.company_access.find_one({"workspace_id": ws_id, "company_id": cid, "user_id": aid})
            if exists:
                report["skipped"] += 1
                continue
            role = "principal"
            # un seul principal par société : le 1er admin est principal, les suivants collaborator
            has_principal = await db.company_access.find_one({"workspace_id": ws_id, "company_id": cid, "role": "principal"})
            if has_principal or a is not admins[0]:
                role = "collaborator"
            doc = {"id": str(uuid.uuid4()), "workspace_id": ws_id, "company_id": cid,
                   "user_id": aid, "role": role, "created_at": now()}
            print(f"[+] company_access {a.get('email')} -> {role} @ {c.get('name')}")
            if COMMIT:
                await db.company_access.insert_one(doc)
            report["changed"] += 1

    # 5) journal (Logs) : stamp workspace_id
    missing_logs = await db.journal.count_documents({"workspace_id": {"$exists": False}})
    if missing_logs:
        print(f"[+] journal : stamp workspace_id sur {missing_logs} entrées")
        if COMMIT:
            await db.journal.update_many({"workspace_id": {"$exists": False}}, {"$set": {"workspace_id": ws_id}})
        report["changed"] += 1
    else:
        report["skipped"] += 1

    print("\n=== RAPPORT ===")
    print(f"examinés : {report['examined']}")
    print(f"modifiés : {report['changed']} ({'appliqués' if COMMIT else 'simulés'})")
    print(f"ignorés  : {report['skipped']}")
    for w in report["warnings"]:
        print(f"⚠️  {w}")
    for e in report["errors"]:
        print(f"❌ {e}")
    if not COMMIT:
        print("\n(DRY RUN — relancer avec --commit pour appliquer)")


if __name__ == "__main__":
    asyncio.run(main())
