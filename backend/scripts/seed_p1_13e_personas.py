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
from core.access import log_scope as ls

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
                  (CA, "accounting.period_close"),
                  # A3 — Ventes & Clients sensitive permissions (approver/poster).
                  (CA, "accounting.customer_invoice_approve"), (CA, "accounting.customer_invoice_post"),
                  (CA, "accounting.customer_payment_post"),
                  (CA, "accounting.customer_credit_note_approve"), (CA, "accounting.customer_credit_note_post"),
                  (CA, "accounting.entry_reverse"), (CA, "accounting.chart_manage")],   # granular: NO period_reopen
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
        "modules": [(CA, "ACCOUNTING", "read"), (CA, "BUDGETS", "read"),
                    (CB, "ACCOUNTING", "manage"), (CB, "CONSOLIDATION", "read")],
        "perms": [(CB, "accounting.entry_post")],   # posting only on company B
    },
    "persona_budgets@accslegro.com": {   # Budgets-only (legacy-route gating test)
        "name": "Persona — Budgets uniquement",
        "companies": [(CA, "company_user", "user")],
        "modules": [(CA, "BUDGETS", "manage")],
        "perms": [],
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

    # P1.13E — a few PLATFORM-scoped audit events (idempotent) so the Logs
    # plateforme audit tool has searchable/filterable content. Secrets are never
    # written; the write path redacts anyway.
    samples = [
        {"event_type": "client.created", "category": "client", "label": "Client ABC créé",
         "result": "success", "resource": "workspace:ws_demo_abc",
         "metadata": {"ip": "203.0.113.10", "user_agent": "Mozilla/5.0", "request_id": "req_abc001",
                      "after": {"name": "Client ABC", "status": "active"}, "reason": "Onboarding"}},
        {"event_type": "client_admin.replaced", "category": "client_admin", "label": "Admin Client ABC remplacé",
         "result": "success", "resource": "user:usr_old -> usr_new",
         "metadata": {"ip": "203.0.113.11", "user_agent": "Mozilla/5.0", "request_id": "req_abc002",
                      "before": {"admin": "old@abc.test"}, "after": {"admin": "new@abc.test"},
                      "password": "SHOULD_NOT_APPEAR", "activation_token": "tok_secret_xyz"}},
        {"event_type": "support.action", "category": "support", "label": "Action support (réinitialisation invitation)",
         "result": "failure", "resource": "invitation:inv_123",
         "metadata": {"ip": "203.0.113.12", "user_agent": "curl/8.0", "request_id": "req_sup001",
                      "reason": "Invitation expirée"}},
        {"event_type": "platform.config", "category": "platform", "label": "Configuration plateforme modifiée",
         "result": "success", "resource": "config:branding",
         "metadata": {"ip": "203.0.113.13", "user_agent": "Mozilla/5.0", "request_id": "req_cfg001"}},
    ]
    actor = {"id": "platform_seed_actor", "email": "platform@meelora.com", "platform_role": "platform_admin"}
    for s in samples:
        if await db.platform_logs.find_one({"label": s["label"]}):
            continue
        md = dict(s["metadata"])
        md.setdefault("result", s.get("result", "success"))
        if s.get("resource"):
            md.setdefault("resource", s["resource"])
        await ls.write_platform_log(db, actor, event_type=s["event_type"], label=s["label"],
                                    details=s.get("resource", ""), metadata=md)
    print("  seeded platform audit logs (4 samples, secrets redacted)")

    # P1.13E — throwaway account for the email-change E2E (idempotent). Plain
    # workspace user; the E2E round-trips its login email A->B->A.
    ec_email = "emailchange_demo@accslegro.com"
    if not await db.users.find_one({"email": ec_email}):
        res = await db.users.insert_one({
            "email": ec_email, "password_hash": bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode(),
            "name": "Email Change Demo", "role": "user", "workspace_id": WS,
            "status": "active", "created_at": now})
        euid = str(res.inserted_id)
        await db.workspace_memberships.insert_one({
            "_id": f"wsm_{uuid.uuid4().hex}", "workspace_id": WS, "user_id": euid,
            "role": "user", "status": "active", "created_at": now})
        print(f"  seeded email-change demo user {ec_email}")


    # P1.13E — a minimal EXTERNAL client workspace so the platform "Sociétés /
    # Clients -> client -> Accéder -> fiche" flow is testable (idempotent).
    if not await db.workspaces.find_one({"_id": "ws_demo_clientabc"}):
        await db.workspaces.insert_one({
            "_id": "ws_demo_clientabc", "name": "Client Démo ABC", "jurisdiction": "CA",
            "organization_type": "company", "status": "active", "created_at": now})
        print("  seeded external demo client workspace (ws_demo_clientabc)")

    print("\nP1.13E personas seeded (idempotent). Password:", PWD)
    client.close()


if __name__ == "__main__":
    asyncio.run(run())
