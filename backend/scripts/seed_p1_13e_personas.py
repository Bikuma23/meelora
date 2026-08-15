"""P1.13E — Persona sign-off seed (idempotent, TEST personas only).

Creates realistic personas B–H with PRECISE, explicit access so the security
matrix can be validated end-to-end. Persona A (platform_admin) reuses the
existing platform@meelora.com identity. No business logic, no financial data
touched. All access is granted through the governed access service functions
(which themselves enforce entitlement rules), never by writing raw grants.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.access import module_access as ma
from core.access import scopes as sc

WS = "ws_56c492936ea64c4db53a2f14a0825ef5"
CA = "965f0770-8cf2-4199-a99f-819ff270436a"   # Meelora (acct)
CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"   # 9434-3977 QC inc. (qc9434)
PWD = "persona123"
ACTOR = "seed_p1_13e"


def _hash(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


# persona -> config
PERSONAS = {
    "persona_employe@accslegro.com": {   # B — Meelora employee (viewer)
        "name": "Persona B — Employé Meelora",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "ACCOUNTING", "read"), (CA, "REPORTING", "read")],
        "perms": [],
    },
    "persona_clientadmin@accslegro.com": {  # C — Client Admin (local admin)
        "name": "Persona C — Client Admin",
        "companies": [(CA, "company_user", "admin")],
        "modules": [],   # admin != financial authority (no auto module access)
        "perms": [],
    },
    "persona_junior@accslegro.com": {    # D — Junior Comptabilité
        "name": "Persona D — Junior Comptabilité",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "ACCOUNTING", "contribute")],
        "perms": [],   # cannot post to GL, cannot close a period
    },
    "persona_finance@accslegro.com": {   # E — Responsable financier
        "name": "Persona E — Responsable financier",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "ACCOUNTING", "manage")],
        "perms": [(CA, "accounting.entry_post"), (CA, "accounting.reconciliation_approve"),
                  (CA, "accounting.period_close")],   # granular: NO period_reopen
    },
    "persona_reporting@accslegro.com": {  # F — Responsable Reporting
        "name": "Persona F — Responsable Reporting",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "REPORTING", "manage")],
        "perms": [(CA, "reporting.report_finalize")],   # NO accounting/FA/consol
    },
    "persona_multi@accslegro.com": {     # G — Multi-société (different rights A vs B)
        "name": "Persona G — Utilisateur multi-société",
        "companies": [(CA, "company_user", "user"), (CB, "company_user", "user")],
        "modules": [(CA, "ACCOUNTING", "read"), (CB, "ACCOUNTING", "manage")],
        "perms": [(CB, "accounting.entry_post")],   # posting only on company B
    },
    "persona_consol@accslegro.com": {    # H — Responsable Consolidation
        "name": "Persona H — Responsable Consolidation",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "CONSOLIDATION", "read")],
        "perms": [],
        "group_scopes": ["group_alpha"],   # scoped; group_beta must be denied
    },
}


async def run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    for email, cfg in PERSONAS.items():
        ex = await db.users.find_one({"email": email})
        if ex:
            uid = str(ex["_id"])
            await db.users.update_one({"_id": ex["_id"]}, {"$set": {
                "platform_role": None, "status": "active", "identity_status": "active",
                "workspace_id": WS, "role": "user"}})
        else:
            res = await db.users.insert_one({
                "email": email, "password_hash": _hash(PWD), "name": cfg["name"],
                "role": "user", "status": "active", "identity_status": "active",
                "platform_role": None, "workspace_id": WS, "created_at": now})
            uid = str(res.inserted_id)
        # workspace membership (organizational only, role=user)
        if not await db.workspace_memberships.find_one({"workspace_id": WS, "user_id": uid}):
            await db.workspace_memberships.insert_one({
                "_id": f"wsm_{uuid.uuid4().hex}", "workspace_id": WS, "user_id": uid,
                "role": "user", "status": "active", "created_at": now})
        for cid, mtype, role in cfg["companies"]:
            if not await db.company_memberships.find_one({"workspace_id": WS, "company_id": cid, "user_id": uid}):
                await db.company_memberships.insert_one({
                    "_id": f"cm_{uuid.uuid4().hex}", "workspace_id": WS, "company_id": cid,
                    "user_id": uid, "membership_type": mtype, "role": role,
                    "status": "active", "created_at": now})
        for cid, mod, lvl in cfg.get("modules", []):
            await ma.set_user_module_access(db, WS, cid, uid, mod, lvl, ACTOR)
        for cid, perm in cfg.get("perms", []):
            await ma.set_user_permission(db, WS, cid, uid, perm, True, ACTOR)
        for gid in cfg.get("group_scopes", []):
            await sc.set_group_scope(db, WS, uid, gid, True, ACTOR)
        print(f"  seeded {email} -> uid {uid}")
    print("\nP1.13E personas seeded (idempotent). Password:", PWD)
    client.close()


if __name__ == "__main__":
    asyncio.run(run())
